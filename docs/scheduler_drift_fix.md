# 调度器秒级漂移修复

## 现象

mariadb-prod-01 采集间隔设置为 600 秒，但每次采集的秒部分持续增长：

```
13:03:42  ← +10m05s
12:53:38  ← +10m05s  
12:43:33  ← +10m05s
12:33:28  ← 基准
```

每轮比预期晚 4~5 秒，累积漂移。

## 根因

原 `_schedule_next()` 在采集完成后以**当前时刻**为基准创建下一个 Timer：

```python
# 旧代码
def _schedule_next(self):
    self._timer = threading.Timer(self.interval, self._run)  # interval 秒后 → 现在 + 600s
```

时间线：
```
12:33:28.0  — _run() 开始
12:33:32.5  — _do_collect() 完成（耗时 4.5s）
12:33:32.5  — _schedule_next()，Timer(600) → 12:43:32.5 触发   ← 漂移了 4.5s
12:43:32.5  — 下一轮触发
12:43:37.0  — 采集完成（耗时 4.5s）
12:43:37.0  — _schedule_next()，Timer(600) → 12:53:37.0 触发   ← 累计漂移 9s
```

每次采集耗时 ~4.5s 被叠加到间隔里，形成 `interval + 采集耗时` 的累积漂移。

## 修复

`_run()` 启动时记录 `run_start = time.time()`，传递给 `_schedule_next()`。
`_schedule_next()` 用 `interval - (当前时间 - run_start)` 计算剩余延迟：

```python
def _run(self):
    run_start = time.time()
    try:
        # ... 采集工作（耗时 ~4.5s）
    finally:
        self._schedule_next(run_start=run_start)

def _schedule_next(self, *, run_start=None):
    if run_start is not None:
        elapsed = time.time() - run_start
        delay = self.interval - elapsed   # 补回已消耗的时间
        if delay < 0:
            delay = 0.5
    else:
        delay = self.interval             # 首次启动，无需补偿
    self._timer = threading.Timer(delay, self._run)
```

修复后时间线：
```
12:33:28.0  — run_start 记录
12:33:32.5  — 采集完成，elapsed=4.5, delay=600-4.5=595.5s
12:43:28.0  — 准时触发 ✓
12:43:28.0  — run_start 记录
12:43:32.5  — 采集完成，elapsed=4.5, delay=600-4.5=595.5s  
12:53:28.0  — 准时触发 ✓
```

秒部分固定在 xx:x3:28，不再漂移。

## 影响范围

三个调度器统一修复：

| 调度器 | 旧行为 | 新行为 |
|---|---|---|
| `_InstanceScheduler` | `Timer(600)` 从采集完成时刻算 | `Timer(600 - elapsed)` 补偿 |
| `LockScheduler` | `Timer(30/5)` 从快照完成时刻算 | 同上，且切频时也传入 run_start |
| `_DeadQueueScheduler` | `Timer(300)` 从探测完成时刻算 | 同上 |
