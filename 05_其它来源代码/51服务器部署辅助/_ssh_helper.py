import os
#!/usr/bin/env python3
"""51 服务器 paramiko SSH 助手：带密码连接、执行只读/运维命令。
用法：
  py -3.12 _ssh_helper.py "命令1; 命令2"
"""
import sys
import paramiko

HOST = os.environ.get("DEPLOY_SSH_HOST", "")      # 51 服务器地址，见部署文档
USER = os.environ.get("DEPLOY_SSH_USER", "")
PASS = os.environ.get("DEPLOY_SSH_PASS", "")      # 凭据只走环境变量，勿写入文件


def run(cmd: str, timeout: int = 60) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=22, username=USER, password=PASS, timeout=20, banner_timeout=20)
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        result = out
        if err.strip():
            result += "\n[STDERR]\n" + err
        if rc != 0:
            result += f"\n[EXIT={rc}]"
        return result
    finally:
        client.close()


if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:])
    if not cmd:
        print("Usage: python _ssh_helper.py '<remote command>'")
        sys.exit(1)
    print(run(cmd))