import json
import uuid
from datetime import datetime

class SocketMessage:
    def __init__(self, message_type, payload, app_id='server'):
        self.message_type = message_type
        self.message_id = str(uuid.uuid4())
        self.timestamp = datetime.now().isoformat()
        self.payload = payload
        self.app_id = app_id

    def to_json(self):
        return json.dumps({
            "message_type": self.message_type,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "app_id": self.app_id,
        })

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        msg = SocketMessage(data["message_type"], data["payload"], data["app_id"])
        msg.message_id = data["message_id"]
        msg.timestamp = data["timestamp"]
        return msg
