import json

from common.daemon_client import DaemonClient

from .data_presenter import DataPresenter


class Client:
    """CLI-facing client: delegates transport and renders command responses."""

    def __init__(self, daemon_client=None):
        self.daemon_client = daemon_client or DaemonClient()

    def execute(self, payload):
        return self.daemon_client.request(payload)

    @staticmethod
    def render(response, output_format):
        if output_format == 'verbose':
            print(json.dumps({'message_type': 'response', 'payload': response}, indent=2))
        elif output_format == 'json':
            print(json.dumps(response, indent=2))
        else:
            DataPresenter.print_output(response)
