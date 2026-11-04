"""程序说明：在测试模块导入前，将默认应用重定向到临时数据库。"""

import os
import tempfile


# app.main 在导入时创建默认应用；pytest 会先加载本文件，确保它不碰真实存档。
_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="localhero-tests-")
os.environ["GREY_ZONE_DB"] = os.path.join(_TEST_RUNTIME.name, "default-import.db")
