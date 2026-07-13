# 2026-07-12 Controller 与 LeaseKeeper 学习总结

## 我遇到的具体 agent engineering 问题

为了让 No.9 到 No.12 并行运行，我一度为每个任务启动一个独立的
Controller 进程。这样能工作，但把“调度多个 sandbox”和“维护单个任务的
lease”混在了一起，也让我难以判断 Controller、进程、线程和协程分别负责
什么。

原来的 `SandboxController._run_task()` 同时创建 E2B 执行 task、续租 task，
再用 `asyncio.wait(..., FIRST_COMPLETED)` 协调它们。逻辑正确，但任务生命周期
细节占据了 Controller，未来加入单 Controller 多 sandbox 并发时会越来越难读。

## 我是怎么解决的

我把续租生命周期提取成 `LeaseKeeper` async context manager。现在核心调用可以
读成：

```python
async with LeaseKeeper(store, task.id, worker_id, ttl, interval):
    result = await e2b.run_task(task)

await store.complete_task(task.id, result, worker_id)
```

`async with` 本身不会创建新进程或线程。`LeaseKeeper.__aenter__()` 使用
`asyncio.create_task()`，在同一个 Controller 进程、同一个 event loop 内启动
续租协程。它定时向 Supabase 更新该任务的 `lease_expires_at`。

`LeaseKeeper.__aexit__()` 设置停止信号并等待续租协程退出。若续租发现
`worker_id` 已不再拥有任务，它会取消拥有它的 Controller task；取消会传递到
正在等待的 E2B runtime，runtime 随后销毁 sandbox。Controller 将结果识别为
`lost_lease`，不会错误写入 `done` 或 `failed`。

测试覆盖了两个关键事实：正常离开 context 后不再续租；lease 丢失时 context
body 会被取消并抛出 `LeaseLostError`。完整 infra 测试共 14 项通过。

## 它如何对应 agent engineering 指导

这属于 long-running agent harness 的生命周期隔离：调度器负责选择和并发，
task-scoped 组件负责 lease、取消和清理。Anthropic 的
[Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
强调让长任务具备清晰、可恢复、可观察的外部控制结构。这里 Supabase 是持久化
状态，LeaseKeeper 是任务存活信号，E2B 是可随时销毁的执行环境。

## 下次我应该记住什么

- 一个 Controller 可以管理多个 E2B sandbox，不需要一任务一进程。
- 每个任务需要自己的执行协程和 LeaseKeeper 协程，但它们共享 Controller 进程。
- lease 必须由 sandbox 外部维护；即使 E2B 卡住，Controller 仍能停止续租并销毁它。
- 把资源生命周期封装进 `async with`：进入时启动，退出时清理，失败时取消所有者。
- 下一步实现并发时，让 Controller 使用 semaphore 限制 sandbox 数量；不要把续租
  逻辑重新塞回调度循环。
