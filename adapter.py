"""
This program is free software: you can redistribute it under the terms
of the GNU General Public License, v. 3.0. If a copy of the GNU General
Public License was not distributed with this file, see <https://www.gnu.org/licenses/>.
"""

from protocol_interfaces import OAuth2ProtocolInterface
from logutils import get_logger

logger = get_logger(__name__)


class MastodonOAuth2Adapter(OAuth2ProtocolInterface):
    """Adapter for integrating Mastodon's OAuth2 protocol."""

    def get_authorization_url(self, **kwargs):
        return super().get_authorization_url(**kwargs)

    def exchange_code_and_fetch_user_info(self, code, **kwargs):
        return super().exchange_code_and_fetch_user_info(code, **kwargs)

    def revoke_token(self, token, **kwargs):
        return super().revoke_token(token, **kwargs)

    def send_message(self, token, message, **kwargs):
        return super().send_message(token, message, **kwargs)
