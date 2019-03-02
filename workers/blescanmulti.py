import time
from interruptingcow import timeout
from bluepy.btle import Scanner, DefaultDelegate
from mqtt import MqttMessage
from utils import booleanize
from workers.base import BaseWorker
from logger import _LOGGER

REQUIREMENTS = ['bluepy']


class ScanDelegate(DefaultDelegate):
  def __init__(self):
    DefaultDelegate.__init__(self)

  def handleDiscovery(self, dev, isNewDev, isNewData):
    if isNewDev:
      _LOGGER.debug("Discovered new device: %s" % dev.addr)


class BleDeviceStatus:
  def __init__(self, worker, mac: str, name: str, available: bool = False, last_status_time: float = None,
               message_sent: bool = True):
    if last_status_time is None:
      last_status_time = time.time()

    self.worker = worker  # type: BlescanmultiWorker
    self.mac = mac.lower()
    self.name = name
    self.available = available
    self.last_status_time = last_status_time
    self.message_sent = message_sent

  def set_status(self, available):
    if available != self.available:
      self.available = available
      self.last_status_time = time.time()
      self.message_sent = False
      return True
    return False

  def _timeout(self):
    if self.available:
      return self.worker.available_timeout
    else:
      return self.worker.unavailable_timeout

  def has_time_elapsed(self):
    elapsed = time.time() - self.last_status_time
    return elapsed > self._timeout()

  def payload(self):
    if self.available:
      return self.worker.available_payload
    else:
      return self.worker.unavailable_payload

  def generate_message(self, device):
    if not self.message_sent and self.has_time_elapsed():
      self.message_sent = True
      return MqttMessage(topic=device.format_topic('presence/{}'.format(self.name)), payload=self.payload())


class BlescanmultiWorker(BaseWorker):
  # Default values
  devices = {}
  # Payload that should be send when device is available
  available_payload = 'home'  # type: str
  # Payload that should be send when device is unavailable
  unavailable_payload = 'not_home'  # type: str
  # After what time (in seconds) we should inform that device is available (default: 0 seconds)
  available_timeout = 0  # type: float
  # After what time (in seconds) we should inform that device is unavailable (default: 60 seconds)
  unavailable_timeout = 60  # type: float
  scan_timeout = 10.  # type: float
  scan_passive = "true"  # type: str

  def __init__(self, **kwargs):
    super(BlescanmultiWorker, self).__init__(**kwargs)
    self.scanner = Scanner().withDelegate(ScanDelegate())
    self.last_status = [
      BleDeviceStatus(self, name, mac) for name, mac in self.devices.items()
    ]

  def searchmac(self, devices, mac):
    for dev in devices:
      if dev.addr == mac.lower():
         return dev

    return None

  def status_update(self):
    devices = self.scanner.scan(float(self.scan_timeout), passive=booleanize(self.scan_passive))
    ret = []

    for name, mac in self.devices.items():
      device = self.searchmac(devices, mac)
      if device is None:
        ret.append(MqttMessage(topic=self.format_topic('presence/'+name), payload=self.available_payload))
      else:
        ret.append(MqttMessage(topic=self.format_topic('presence/'+name+'/rssi'), payload=device.rssi))
        ret.append(MqttMessage(topic=self.format_topic('presence/'+name), payload=self.unavailable_payload))

    return ret
