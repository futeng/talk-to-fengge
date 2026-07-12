"""进程入口；在主线程预注册豆包 LiveKit 插件。"""

from livekit.plugins import bytedance  # noqa: F401

from worker.agent import main


main()
