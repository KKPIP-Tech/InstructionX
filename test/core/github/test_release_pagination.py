"""GitHub Release 完整分页读取测试。"""

import pytest

from core.github import GitHubNetworkError


class TestListAllReleases:
    """验证框架更新检查可读取全部 Release，而非固定页数上限。"""

    def test_reads_until_short_page(self, api_client, fake_response):
        """满一百条时应继续翻页，并在短页后停止。"""
        client, session = api_client
        first_page = [{"id": index} for index in range(100)]
        session.request.side_effect = [
            fake_response(payload=first_page),
            fake_response(payload=[{"id": 100}]),
        ]

        releases = client.list_all_releases("owner", "repo")

        assert len(releases) == 101
        calls = session.request.call_args_list
        assert [call.kwargs["params"]["page"] for call in calls] == [1, 2]
        assert all(call.kwargs["params"]["per_page"] == 100 for call in calls)

    def test_rejects_non_list_response(self, api_client, fake_response):
        """Release 响应不是数组时应报网络数据错误，而非静默返回。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={"message": "bad"})

        with pytest.raises(GitHubNetworkError, match="Release"):
            client.list_all_releases("owner", "repo")
