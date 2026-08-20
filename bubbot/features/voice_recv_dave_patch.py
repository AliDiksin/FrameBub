"""Runtime patch for discord-ext-voice-recv DAVE receive support.

This carries the small unmerged upstream fix from:
https://github.com/imayhaveborkedit/discord-ext-voice-recv/pull/54

Remove this module when discord-ext-voice-recv releases equivalent DAVE
decryption support.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def apply_voice_recv_dave_patch() -> bool:
    """Patch discord-ext-voice-recv packet decoding for DAVE voice channels."""
    try:
        from discord.ext.voice_recv import opus as opus_mod
        from discord.ext.voice_recv import router as router_mod
    except ImportError:
        return False

    packet_decoder = opus_mod.PacketDecoder
    packet_router = router_mod.PacketRouter
    if getattr(packet_decoder, "_bub_dave_patch_applied", False):
        return True

    try:
        from davey import MediaType
        has_dave = True
    except ImportError:
        MediaType = None
        has_dave = False

    original_init = packet_decoder.__init__

    def patched_init(self, router, ssrc):
        original_init(self, router, ssrc)
        self.vc = self.sink.voice_client
        dave_session = getattr(getattr(self.vc, "_connection", None), "dave_session", None)
        if dave_session is not None and hasattr(dave_session, "set_passthrough_mode"):
            try:
                dave_session.set_passthrough_mode(True, 10)
            except Exception as exc:
                log.debug("DAVE passthrough setup failed: %s", exc)

    def patched_process_packet(self, packet):
        pcm = None
        member = self._get_cached_member()

        payload = getattr(packet, "payload", 120)
        if payload != 120:
            return None

        if member is None:
            self._cached_id = self.sink.voice_client._get_id_from_ssrc(self.ssrc)  # type: ignore[attr-defined]
            member = self._get_cached_member()

        dave_session = getattr(getattr(self.vc, "_connection", None), "dave_session", None)
        should_decrypt = (
            has_dave
            and MediaType is not None
            and member is not None
            and not packet.is_silence()
            and getattr(packet, "decrypted_data", None) is not None
            and dave_session is not None
            and getattr(dave_session, "ready", False)
        )
        if should_decrypt:
            try:
                packet.decrypted_data = dave_session.decrypt(
                    member.id,
                    MediaType.audio,
                    bytes(packet.decrypted_data),
                )
            except Exception as exc:
                log.debug("DAVE packet decrypt failed for ssrc=%s: %s", self.ssrc, exc)
                self._last_seq = packet.sequence
                self._last_ts = packet.timestamp
                return opus_mod.VoiceData(packet, None, pcm=b"")

        if not self.sink.wants_opus():
            packet, pcm = self._decode_packet(packet)

        data = opus_mod.VoiceData(packet, member, pcm=pcm)
        self._last_seq = packet.sequence
        self._last_ts = packet.timestamp
        return data

    def patched_decode_packet(self, packet):
        assert self._decoder is not None

        if packet:
            try:
                pcm = self._decoder.decode(packet.decrypted_data, fec=False)
            except Exception as exc:
                log.debug("Opus decode failed for ssrc=%s: %s", self.ssrc, exc)
                pcm = self._decoder.decode(None, fec=False)
            return packet, pcm

        next_packet = self._buffer.peek_next()
        if next_packet is not None:
            nextdata = next_packet.decrypted_data
            pcm = self._decoder.decode(nextdata, fec=True)
        else:
            pcm = self._decoder.decode(None, fec=False)
        return packet, pcm

    def patched_do_run(self):
        while not self._end_thread.is_set():
            self.waiter.wait()
            with self._lock:
                for decoder in self.waiter.items:
                    data = decoder.pop_data()
                    if data is not None and data.source is not None:
                        self.sink.write(data.source, data)

    packet_decoder.__init__ = patched_init
    packet_decoder._process_packet = patched_process_packet
    packet_decoder._decode_packet = patched_decode_packet
    packet_router._do_run = patched_do_run
    packet_decoder._bub_dave_patch_applied = True
    return True
