"""Streetfighterdle Activity slash-command synchronization helpers."""
# Activity registration stays separate from the general slash-command tree wiring.

import os

import aiohttp
import discord


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


async def _post_activity_entry_command(session, url, payload, authorization_label, authorization_value):
    headers = {"Authorization": authorization_value, "Content-Type": "application/json"}
    async with session.post(url, headers=headers, json=payload) as response:
        body = await response.text()
        if response.status >= 400:
            print(
                f"[streetfighterdle] primary entry command registration failed "
                f"auth={authorization_label} status={response.status}: {body[:300]}",
                flush=True,
            )
            return False
    print(
        f"[streetfighterdle] Primary Activity entry command registered via {authorization_label}.",
        flush=True,
    )
    return True


def _streetfighterdle_activity_entry_payload():
    return {
        "name": "Streetfighterdle",
        "description": "Launch Streetfighterdle Activity",
        "type": 4,
        "handler": 2,
        "integration_types": [0],
        "contexts": [0],
    }


async def _bulk_sync_global_commands_with_activity_entry(client, tree, local_commands):
    application_id = _env_int("STREETFIGHTERDLE_ACTIVITY_APPLICATION_ID", 0)
    if not application_id:
        application_id = getattr(client, "application_id", None) or getattr(getattr(client, "user", None), "id", None)
    token = os.getenv("DISCORD_TOKEN")
    if not application_id or not token:
        return None

    payload = [command.to_dict(tree) for command in local_commands]
    payload = [command for command in payload if int(command.get("type", 1) or 1) != 4]
    payload.append(_streetfighterdle_activity_entry_payload())
    url = f"https://discord.com/api/v10/applications/{application_id}/commands"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=payload) as response:
            body = await response.text()
            if response.status >= 400:
                print(
                    f"[menu] Global slash/activity command raw sync failed "
                    f"status={response.status}: {body[:500]}",
                    flush=True,
                )
                return None
            try:
                return await response.json(content_type=None)
            except Exception:
                print(f"[menu] Global slash/activity command raw sync returned invalid JSON: {body[:500]}", flush=True)
                return None


async def _delete_existing_activity_entry_commands(session, application_id, authorization_label, authorization_value):
    base_url = f"https://discord.com/api/v10/applications/{application_id}/commands"
    headers = {"Authorization": authorization_value}
    async with session.get(base_url, headers=headers) as response:
        body = await response.text()
        if response.status >= 400:
            print(
                f"[streetfighterdle] primary entry command lookup failed "
                f"auth={authorization_label} status={response.status}: {body[:300]}",
                flush=True,
            )
            return False
        try:
            commands = await response.json(content_type=None)
        except Exception:
            print(f"[streetfighterdle] primary entry command lookup returned invalid JSON: {body[:300]}", flush=True)
            return False
    deleted_any = False
    for command in commands or []:
        if int(command.get("type", 0) or 0) != 4:
            continue
        command_id = command.get("id")
        if not command_id:
            continue
        async with session.delete(f"{base_url}/{command_id}", headers=headers) as response:
            body = await response.text()
            if response.status >= 400:
                print(
                    f"[streetfighterdle] primary entry command delete failed "
                    f"auth={authorization_label} status={response.status}: {body[:300]}",
                    flush=True,
                )
                return False
        deleted_any = True
    if deleted_any:
        print(f"[streetfighterdle] Deleted existing Primary Activity entry command via {authorization_label}.", flush=True)
    return True


async def _discord_client_credentials_token(session, application_id):
    client_secret = (
        os.getenv("DISCORD_CLIENT_SECRET")
        or os.getenv("DISCORD_APPLICATION_CLIENT_SECRET")
        or ""
    ).strip()
    if not client_secret:
        return None
    data = {
        "grant_type": "client_credentials",
        "scope": "applications.commands.update",
    }
    async with session.post(
        "https://discord.com/api/v10/oauth2/token",
        data=data,
        auth=aiohttp.BasicAuth(str(application_id), client_secret),
    ) as response:
        payload = await response.json(content_type=None)
        if response.status >= 400:
            print(
                f"[streetfighterdle] client-credentials token request failed "
                f"status={response.status}: {str(payload)[:300]}",
                flush=True,
            )
            return None
    return payload.get("access_token")


async def _register_streetfighterdle_activity_entry_command(client):
    application_id = _env_int("STREETFIGHTERDLE_ACTIVITY_APPLICATION_ID", 0)
    if not application_id:
        application_id = getattr(client, "application_id", None) or getattr(getattr(client, "user", None), "id", None)
    token = os.getenv("DISCORD_TOKEN")
    if not application_id or not token:
        return
    payload = _streetfighterdle_activity_entry_payload()
    url = f"https://discord.com/api/v10/applications/{application_id}/commands"
    try:
        async with aiohttp.ClientSession() as session:
            if await _post_activity_entry_command(session, url, payload, "bot", f"Bot {token}"):
                return
            bearer_token = await _discord_client_credentials_token(session, application_id)
            if bearer_token:
                await _post_activity_entry_command(session, url, payload, "client_credentials", f"Bearer {bearer_token}")
    except Exception as error:
        print(f"[streetfighterdle] primary entry command registration error: {error}", flush=True)


async def _delete_streetfighterdle_activity_entry_command(client):
    application_id = _env_int("STREETFIGHTERDLE_ACTIVITY_APPLICATION_ID", 0)
    if not application_id:
        application_id = getattr(client, "application_id", None) or getattr(getattr(client, "user", None), "id", None)
    token = os.getenv("DISCORD_TOKEN")
    if not application_id or not token:
        return
    try:
        async with aiohttp.ClientSession() as session:
            if await _delete_existing_activity_entry_commands(session, application_id, "bot", f"Bot {token}"):
                return
            bearer_token = await _discord_client_credentials_token(session, application_id)
            if bearer_token:
                await _delete_existing_activity_entry_commands(session, application_id, "client_credentials", f"Bearer {bearer_token}")
    except Exception as error:
        print(f"[streetfighterdle] primary entry command cleanup error: {error}", flush=True)


async def sync_public_slash_commands(client, tree):
    """Sync global commands and clear stale guild-scoped copies."""
    local_commands = list(tree.get_commands())
    local_names = [cmd.name for cmd in local_commands]
    if len(local_names) != len(set(local_names)):
        print(f"[menu] WARNING: duplicate slash names in local tree: {local_names}", flush=True)

    guild_ids_to_clear = set()
    channel_id = os.getenv("CHANNEL_ID")
    if channel_id:
        try:
            channel = client.get_channel(int(channel_id))
            if channel and getattr(channel, "guild", None):
                guild_ids_to_clear.add(int(channel.guild.id))
        except (TypeError, ValueError):
            pass
    for env_name in ("DISCORD_GUILD_ID", "GUILD_ID"):
        raw_guild_id = os.getenv(env_name)
        if not raw_guild_id:
            continue
        try:
            guild_ids_to_clear.add(int(raw_guild_id))
        except ValueError:
            print(f"[menu] Ignoring invalid {env_name}={raw_guild_id!r}", flush=True)

    for guild_id in sorted(guild_ids_to_clear):
        guild_obj = discord.Object(id=guild_id)
        tree.clear_commands(guild=guild_obj)
        await tree.sync(guild=guild_obj)
        print(f"[menu] Cleared guild-scoped slash commands for guild {guild_id}", flush=True)

    raw_synced = await _bulk_sync_global_commands_with_activity_entry(client, tree, local_commands)
    if raw_synced is not None:
        synced_names = sorted(
            f"{command.get('name')}" + (" (activity)" if int(command.get("type", 1) or 1) == 4 else "")
            for command in raw_synced
            if command.get("name")
        )
        print(
            f"[menu] Global slash/activity commands synced ({len(synced_names)}): "
            + ", ".join(f"/{name}" for name in synced_names),
            flush=True,
        )
        return raw_synced

    await _delete_streetfighterdle_activity_entry_command(client)
    synced = await tree.sync()
    synced_names = sorted(cmd.name for cmd in synced)
    print(
        f"[menu] Global slash commands synced ({len(synced_names)}): "
        + ", ".join(f"/{name}" for name in synced_names),
        flush=True,
    )
    if len(synced_names) != len(set(synced_names)):
        print("[menu] WARNING: Discord sync returned duplicate command names", flush=True)
    await _register_streetfighterdle_activity_entry_command(client)
    return synced
