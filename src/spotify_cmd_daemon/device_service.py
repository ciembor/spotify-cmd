"""Spotify Connect device discovery and activation."""


class SpotifyDeviceService:
    def __init__(self, client, device_name=None):
        self.client = client
        self.device_name = device_name
        self.device_id = None

    def refresh(self):
        devices = self.client.devices().get('devices', [])
        if self.device_name:
            device = next((entry for entry in devices if entry.get('name') == self.device_name), None)
            if not device:
                raise RuntimeError(f"Device '{self.device_name}' not found.")
        else:
            device = next((entry for entry in devices if entry.get('is_active')), None)
            device = device or next(iter(devices), None)
            if not device:
                raise RuntimeError('No active device found.')
        self.device_id = device['id']
        return device

    def ensure_active(self, force_play=False, retries=2, delay=1, sleep=None):
        sleep = sleep or (lambda _: None)
        last_error = None
        for _ in range(retries):
            try:
                device = self.refresh()
                if self.device_name and not device.get('is_active'):
                    self.client.transfer_playback(device_id=self.device_id, force_play=force_play)
                return device
            except Exception as error:
                last_error = error
                sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError(f"Device '{self.device_name}' could not be activated.")
