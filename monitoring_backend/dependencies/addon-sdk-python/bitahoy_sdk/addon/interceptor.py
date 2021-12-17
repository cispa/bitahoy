from bitahoy_sdk.addon.utils import Device
from bitahoy_sdk.stubs.addon import Interceptor, InterceptorAPI
from typing import List


class InterceptorAddon(Interceptor):

    def __init__(self):
        pass

    async def main(self):
        # your main "thread"
        pass

    def __emulator__get_token(self, url):
        # only for the emulator. normally the framework takes care of this, just hardcode a valid token for testing here 
        return {'code': 'xxxxxxxxxxxxxxxx', 'id': 1196070889, 'perm': -1, 'time': 1627636720, 'belongs': None, 'signature': 'ZAV6lgNXncpeEBjTUgGnJ3MtOL2Qinjvdc4Ai9DrJx185Yz8tACBlHNVnX3S7wYZES8ahsWBLN8qKxo7/3ccNQU+tV1b8lbIgzwSJWkcNWLPLRNaKEqYgedUEcX/P2rQ1s3nfqxT8Yre2HD91RBuim7wIgM/uUQENQJ16eCAd1xRo2UiO3d6HaKpQdmrDH3x1O1nrdy0QmMLsy35aHZAoUUSAytu1RY/hGAP4mJr0h9sLu/7xhLSFrruTx9ovz73D/1OQMpiD9Zgw5dPtN+tx8e41S/zOaIigcHNjVuCmI7guCiSNAeEUwoxBoCkKmXENfZ0Jege70yZtvKIxsWPXQ=='}