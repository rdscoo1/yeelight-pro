DOMAIN = 'yeelight_pro'
DEFAULT_NAME = 'Yeelight Pro'

CONF_GATEWAYS = 'gateways'
CONF_PID = 'pid'
CONF_KEEPALIVE = 'keepalive'
CONF_TRANSITION_TIME = 'transition_time'

DEFAULT_KEEPALIVE = 30
MIN_KEEPALIVE = 10
MAX_KEEPALIVE = 300

DEFAULT_TRANSITION_TIME = 5.0
MIN_TRANSITION_TIME = 0.5
MAX_TRANSITION_TIME = 30.0

SUPPORTED_DOMAINS = [
    'button',
    'sensor',
    'switch',
    'light',
    'number',
    'binary_sensor',
    'cover',
    'climate',
    'update',
]

PID_GATEWAY = 1
PID_WIFI_PANEL = 2

GATEWAY_TYPES = {
    PID_GATEWAY: 'Gateway Pro (网关)',
    PID_WIFI_PANEL: 'Wifi Panel (全面屏)',
}
