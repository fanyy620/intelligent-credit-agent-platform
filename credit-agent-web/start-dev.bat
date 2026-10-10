@echo off
chcp 65001 >nul
setlocal
rem ====================================================================
rem  credit-agent-web 开发环境一键启动引导（Windows）
rem  按顺序拉起：Redis(若有) -^> Python Agent -^> SSM 后端 -^> 前端
rem ====================================================================

title credit-agent-web 开发环境启动引导

echo ================================================================
echo   智能信贷营销与咨询平台 - 开发环境启动引导
echo ================================================================
echo.

rem ---- 第 0 步：依赖探测 ----
echo [第 0 步] 环境探测：
where java >nul 2>nul && (echo   [OK] Java 已安装) || (echo   [缺失] Java - 后端需要 JDK 8+)
where mvn >nul 2>nul && (echo   [OK] Maven 已安装) || (echo   [缺失] Maven - 后端构建需要)
where node >nul 2>nul && (echo   [OK] Node 已安装) || (echo   [缺失] Node - 前端需要)
where python >nul 2>nul && (echo   [OK] Python 已安装) || (echo   [缺失] Python - Agent 需要)
where redis-server >nul 2>nul && (echo   [OK] Redis 已安装) || (echo   [提示] 未检测到 redis-server，可跳过或用 Docker)
where mysql >nul 2>nul && (echo   [OK] MySQL 已安装) || (echo   [提示] 未检测到 mysql 客户端，后端需 MySQL 8)
echo.

rem ---- 第 1 步：MySQL 初始化 ----
echo [第 1 步] 初始化数据库（仅需首次）：
echo     mysql -uroot -p ^< backend\sql\init.sql
echo.

rem ---- 第 2 步：Redis ----
echo [第 2 步] 启动 Redis（新开一个窗口）：
echo     redis-server
echo.

rem ---- 第 3 步：Python Agent ----
echo [第 3 步] 启动 Python 智能引擎（新开窗口，端口 8000）：
echo     cd ..\credit-agent-platform
echo     python src\api_server.py --port 8000
choice /c YN /m "现在拉起 Python Agent 新窗口吗"
if errorlevel 2 goto :skip_agent
start "credit-agent:8000" cmd /k "cd /d %~dp0..\credit-agent-platform && python src\api_server.py --port 8000"
:skip_agent
echo.

rem ---- 第 4 步：SSM 后端 ----
echo [第 4 步] 启动 SSM 后端（新开窗口，端口 8080，上下文 /credit-web）：
echo     cd backend
echo     mvn tomcat7:run
echo     （首次拉取依赖较慢；生产部署见 docs\deployment-guide.md）
choice /c YN /m "现在拉起后端新窗口吗（需要 JDK+Maven）"
if errorlevel 2 goto :skip_backend
start "credit-web-backend:8080" cmd /k "cd /d %~dp0backend && mvn tomcat7:run"
:skip_backend
echo.

rem ---- 第 5 步：前端 ----
echo [第 5 步] 启动前端（新开窗口，默认 5173；/api 代理到 8080/credit-web）：
echo     cd frontend
echo     npm install   （仅首次）
echo     npm run dev
choice /c YN /m "现在拉起前端新窗口吗"
if errorlevel 2 goto :skip_frontend
if not exist "%~dp0frontend\node_modules" (
    echo 首次运行，先安装前端依赖…
    start "credit-web-frontend" cmd /k "cd /d %~dp0frontend && npm install && npm run dev"
) else (
    start "credit-web-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
)
:skip_frontend
echo.

echo ================================================================
echo   全部启动后访问：
echo     前端        http://localhost:5173
echo     后端健康    http://localhost:8080/credit-web/health
echo     Agent 健康  http://localhost:8000/health
echo   演示账号：admin / 123456（管理员）  manager01 / 123456（客户经理）
echo ================================================================
pause
