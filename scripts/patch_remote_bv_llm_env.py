"""One-shot: enable BV LLM on production .env and restart bub."""
from __future__ import annotations

import argparse
import base64

import paramiko


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="143.110.170.232")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", required=True)
    parser.add_argument("--remote-env", default="/root/bub/.env")
    args = parser.parse_args()

    updates = {"BUB_BV_LLM_ENABLED": "1"}
    remote_script = f"""
from pathlib import Path
p = Path({args.remote_env!r})
lines = p.read_text().splitlines() if p.exists() else []
updates = {updates!r}
out = []
seen = set()
for line in lines:
    if not line.strip() or line.strip().startswith('#') or '=' not in line:
        out.append(line)
        continue
    key = line.split('=', 1)[0].strip()
    if key in updates:
        out.append(f'{{key}}={{updates[key]}}')
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f'{{key}}={{value}}')
p.write_text('\\n'.join(out) + '\\n')
print('BUB_BV_LLM_ENABLED=1')
""".strip()
    encoded = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    remote_cmd = f"python3 -c \"import base64; exec(base64.b64decode('{encoded}').decode('utf-8'))\""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.host,
        username=args.user,
        password=args.password,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        _stdin, stdout, stderr = client.exec_command(remote_cmd)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        if exit_code != 0:
            raise RuntimeError(err or out or f"remote patch failed ({exit_code})")
        if out:
            print(out)
        client.exec_command("systemctl restart bub")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
