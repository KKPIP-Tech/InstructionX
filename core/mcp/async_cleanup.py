"""MCP 自有 asyncio 事件循环的统一任务清理。"""

import asyncio


async def cancel_pending_tasks() -> None:
    """取消当前 loop 中除调用者外的遗留 Task，并等待取消完成。

    仅在传输和服务器已经停止后调用，避免 loop.close() 销毁仍在等待的
    SSE watcher、流式响应或传输后台任务。
    """
    current = asyncio.current_task()
    pending = [
        task for task in asyncio.all_tasks()
        if task is not current and not task.done()
    ]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
