# 志愿讲解员成长管理系统

这是一个以 FastAPI 提供 HTTP 接口、以 SQLite 保存业务数据的 Python 服务端项目。项目覆盖多个相互关联的业务边界，所有验收都可在单个 Linux 应用容器中离线完成，不依赖浏览器、设备或额外运行服务。

## 本地测试

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q test_api_acceptance.py
```

## 编译检查

```bash
python -m compileall -q .
```

## 容器运行

```bash
docker build -t redscarf-service .
docker run --rm -p 8000:8000 redscarf-service
```

启动后可访问 `GET /health` 或根路径确认服务状态。运行测试会使用临时或本地 SQLite 文件，不需要外部数据库。
