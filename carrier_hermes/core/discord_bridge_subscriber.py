from __future__ import annotations
import logging
from carrier_hermes.core.events import ContentDelta, ItemStarted
from carrier_hermes.core.event_bus import HelmEventBus

logger = logging.getLogger("carrier_hermes.discord_bridge_subscriber")


class DiscordBridgeSubscriber:
    """
    Receives streaming events from HelmEventBus and updates Discord.

    content.delta  → accumulate delta text per thread; edit Discord message.
    item.started   → when item_type is a tool, post "Running {title}..." announcement.
    """

    def __init__(self, bus: HelmEventBus) -> None:
        self._buffers: dict[str, str] = {}  # thread_id -> accumulated text
        bus.subscribe(["content.delta", "item.started"], self._handle)

    def _handle(self, event) -> None:
        if isinstance(event, ContentDelta):
            self._buffers[event.thread_id] = self._buffers.get(event.thread_id, "") + event.delta
            self._edit_discord_message(event.thread_id, self._buffers[event.thread_id])
        elif isinstance(event, ItemStarted):
            if event.item_type not in ("text", ""):
                title = event.title or event.item_type
                self._post_tool_announcement(event.thread_id, title)

    def _edit_discord_message(self, thread_id: str, text: str) -> None:
        # TODO: call Discord bot API to edit the in-progress message for thread_id
        logger.debug("discord_bridge: [%s] streaming update (%d chars)", thread_id, len(text))

    def _post_tool_announcement(self, thread_id: str, title: str) -> None:
        # TODO: call Discord bot API to post "Running {title}..." in thread_id's channel
        logger.info("discord_bridge: [%s] tool announced: %s", thread_id, title)
