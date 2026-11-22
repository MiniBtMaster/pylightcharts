"""技能搜索：skills.sh + **GitHub 兜底**（v1.3.8-27）

`skills.sh` 的目录只收录「有人用 `npx skills add` 装过」的仓库（官方 FAQ：
leaderboard 来自安装 telemetry），所以刚发布 / 冷门的 skill 在它索引里要等
几小时到几天 —— 用户实测搜 `minibt` 搜不到自己的 `minibt-strategy` ✗。
现在 `search_skills()` 会**再搜一次 GitHub**（仓库名/描述里带关键词、且根目录
真的有 `SKILL.md`），直接给出可安装的 `owner/repo`。
"""
import json
import urllib.error
import urllib.parse

import pytest

from minibt.desk import pi


# ---------------------------------------------------------------- 工具
def _skills_sh(items):
    return lambda url, timeout=15.0, headers=None: {'skills': items}


def _github(items, calls=None):
    def fake(query, limit=10):
        if calls is not None:
            calls.append(query)
        return {'ok': True, 'items': items}
    return fake


def _offline(url, timeout=15.0, headers=None):
    raise OSError('network down')


GH_ITEM = {
    'name': 'minibt-strategy（GitHub）',
    'package': 'MiniBtMaster/minibt-strategy',
    'source': 'MiniBtMaster/minibt-strategy',
    'installs': '',
    'stars': 1,
    'provider': 'github',
    'url': 'https://github.com/MiniBtMaster/minibt-strategy',
    'description': 'MiniBT 策略开发 Skill',
}


# ---------------------------------------------------------------- 用例
def test_github_fallback_when_skills_sh_returns_nothing(monkeypatch):
    """skills.sh 没结果 → 用 GitHub 的（用户要的就是这个）✓"""
    monkeypatch.setattr(pi, '_fetch', _skills_sh([]))
    monkeypatch.setattr(pi, 'github_search_skills', _github([GH_ITEM]))

    out = pi.search_skills('minibt')
    assert out['ok'] is True
    assert out['source_api'] == 'github'
    assert [row['package'] for row in out['items']] == [
        'MiniBtMaster/minibt-strategy']
    assert out['items'][0]['provider'] == 'github'
    assert 'GitHub' in out['items'][0]['name']
    assert '还没收录' in out.get('note', '')


def test_github_fallback_when_skills_sh_hits_do_not_match(monkeypatch):
    """skills.sh 有结果但**一个都不含关键词**（模糊搜索的老毛病）→ 也补 GitHub"""
    monkeypatch.setattr(pi, '_fetch', _skills_sh([
        {'id': 'a/b/other', 'source': 'a/b', 'name': 'other', 'installs': 3}]))
    monkeypatch.setattr(pi, 'github_search_skills', _github([GH_ITEM]))

    out = pi.search_skills('minibt')
    assert out['source_api'] == 'both'
    assert [row['package'] for row in out['items']] == [
        'a/b', 'MiniBtMaster/minibt-strategy']


def test_skills_sh_hit_matching_query_does_not_call_github(monkeypatch):
    """skills.sh 已经命中关键词 → 不再打 GitHub（省限频）✓"""
    calls = []
    monkeypatch.setattr(pi, '_fetch', _skills_sh([
        {'id': 'MiniBtMaster/minibt-strategy/strategy',
         'source': 'MiniBtMaster/minibt-strategy',
         'name': 'minibt-strategy', 'installs': 7}]))
    monkeypatch.setattr(pi, 'github_search_skills', _github([], calls))

    out = pi.search_skills('minibt', limit=1)
    assert out['source_api'] == 'skills.sh'
    assert calls == []


def test_github_fallback_dedupes_same_repo(monkeypatch):
    """两个来源都给了同一个仓库 → 只留一条（skills.sh 的优先）"""
    monkeypatch.setattr(pi, '_fetch', _skills_sh([
        {'id': 'x/y/z', 'source': 'other/repo', 'name': 'unrelated'}]))
    monkeypatch.setattr(pi, 'github_search_skills', _github([
        GH_ITEM, dict(GH_ITEM, package='other/repo', name='other/repo（GitHub）')]))

    out = pi.search_skills('minibt')
    packages = [row['package'] for row in out['items']]
    assert packages.count('other/repo') == 1, packages


def test_both_down_reports_error_and_hint(monkeypatch):
    monkeypatch.setattr(pi, '_fetch', _offline)
    monkeypatch.setattr(pi, 'github_search_skills',
                        lambda query, limit=10: {'ok': False,
                                                 'error': '连不上 GitHub',
                                                 'items': []})
    out = pi.search_skills('minibt')
    assert out['ok'] is False
    assert 'skills.sh' in out['error']
    assert JSON_KEYS_OK(out)


def JSON_KEYS_OK(out):
    """返回体必须能 JSON 序列化（要经 HTTP 推给前端 ✓）"""
    json.dumps(out)
    return True


def test_empty_query_is_noop(monkeypatch):
    called = []
    monkeypatch.setattr(pi, 'github_search_skills', _github([], called))
    out = pi.search_skills('   ')
    assert out == {'ok': True, 'items': []}
    assert called == []


# ---------------------------------------------------------------- GitHub 那层
def test_github_search_requires_skill_md(monkeypatch):
    """仓库必须**根目录有 `SKILL.md`** 才算 skill（否则装了也没用）"""
    def fake(url, timeout=15.0, headers=None):
        if '/search/repositories' in url:
            return {'items': [
                {'full_name': 'ok/repo', 'name': 'repo', 'html_url': 'u1',
                 'stargazers_count': 9, 'description': 'has skill'},
                {'full_name': 'no/skill', 'name': 'noskill', 'html_url': 'u2',
                 'stargazers_count': 5},
            ]}
        if 'ok/repo/contents/SKILL.md' in url:
            return {'name': 'SKILL.md'}
        raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)

    monkeypatch.setattr(pi, '_fetch', fake)
    pi._GITHUB_CACHE.clear()
    out = pi.github_search_skills('minibt')
    assert out['ok'] is True
    assert [row['package'] for row in out['items']] == ['ok/repo']
    assert out['items'][0]['stars'] == 9


def test_github_search_caches_results(monkeypatch):
    calls = []

    def fake(url, timeout=15.0, headers=None):
        calls.append(url)
        if '/search/repositories' in url:
            return {'items': [{'full_name': 'ok/repo', 'name': 'repo',
                               'stargazers_count': 1}]}
        return {'name': 'SKILL.md'}

    monkeypatch.setattr(pi, '_fetch', fake)
    pi._GITHUB_CACHE.clear()
    first = pi.github_search_skills('minibt', limit=1)
    after_first = len(calls)
    second = pi.github_search_skills('minibt', limit=1)
    assert first['items'], first
    assert second.get('cached') is True
    assert len(calls) == after_first, '第二次不该再打接口（限频）'


def test_owner_repo_query_is_direct_without_network(monkeypatch):
    """直接输 `owner/repo` → 不探测、不打接口（限频时也能装自己的仓库 ✓）"""
    calls = []

    def fake(url, timeout=15.0, headers=None, insecure=False):
        calls.append(url)
        raise AssertionError('不该打接口')

    monkeypatch.setattr(pi, '_fetch', fake)
    monkeypatch.setattr(pi, '_github_fetch', fake)
    pi._GITHUB_CACHE.clear()
    out = pi.github_search_skills('MiniBtMaster/minibt-strategy')
    assert out['ok'] is True and out.get('direct') is True
    assert out['items'][0]['package'] == 'MiniBtMaster/minibt-strategy'
    assert 'GitHub' in out['items'][0]['name']
    assert calls == []


def test_github_search_token_header(monkeypatch):
    """设了 `MINIBT_GITHUB_TOKEN` 就带上（未登录限 60 次/小时）"""
    seen = {}

    def fake(url, timeout=15.0, headers=None):
        seen['headers'] = headers or {}
        if '/search/repositories' in url:
            return {'items': []}
        return {'name': 'SKILL.md'}

    monkeypatch.setattr(pi, '_fetch', fake)
    monkeypatch.setenv('MINIBT_GITHUB_TOKEN', 'tok123')
    pi._GITHUB_CACHE.clear()
    pi.github_search_skills('minibt')
    assert seen['headers'].get('Authorization') == 'Bearer tok123'

def test_github_fetch_retries_insecure_on_cert_error(monkeypatch):
    """证书校验失败（公司代理 / 缺根证书）→ 降级重试一次（公开只读接口）✓"""
    calls = []

    def fake(url, timeout=15.0, headers=None, insecure=False):
        calls.append(insecure)
        if not insecure:
            raise OSError('CERTIFICATE_VERIFY_FAILED: unable to get issuer '
                          'certificate')
        return {'ok': True}

    monkeypatch.setattr(pi, '_fetch', fake)
    monkeypatch.delenv('MINIBT_GITHUB_INSECURE', raising=False)
    out = pi._github_fetch('https://api.github.com/x')
    assert out == {'ok': True}
    assert calls == [False, True], calls


def test_github_fetch_insecure_can_be_disabled(monkeypatch):
    """`MINIBT_GITHUB_INSECURE=0` → 不降级，老老实实报错（安全开关 ✓）"""
    def fake(url, timeout=15.0, headers=None, insecure=False):
        raise OSError('CERTIFICATE_VERIFY_FAILED')

    monkeypatch.setattr(pi, '_fetch', fake)
    monkeypatch.setenv('MINIBT_GITHUB_INSECURE', '0')
    with pytest.raises(OSError):
        pi._github_fetch('https://api.github.com/x')
