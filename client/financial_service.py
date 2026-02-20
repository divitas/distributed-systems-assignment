"""
Financial Transactions Service - SOAP/WSDL
Runs on VM5, port 7000
"""

import random
import sys
import os
from spyne import Application, rpc, ServiceBase, Unicode, Boolean
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server


class FinancialService(ServiceBase):
    @rpc(Unicode, Unicode, Unicode, Unicode, _returns=Boolean)
    def ProcessPayment(ctx, name, card_number, expiration_date, security_code):
        """Process payment - returns True (90%) or False (10%)"""
        if not all([name, card_number, expiration_date, security_code]):
            return False
        if len(card_number) < 13:
            return False
        # 90% success rate as per requirements
        return random.random() < 0.9


application = Application(
    [FinancialService],
    tns='financial.transactions',
    in_protocol=Soap11(validator='lxml'),
    out_protocol=Soap11()
)


if __name__ == '__main__':
    port = 7000
    wsgi_app = WsgiApplication(application)
    server = make_server('0.0.0.0', port, wsgi_app)
    print(f"Financial SOAP service running on port {port}")
    print(f"WSDL available at: http://0.0.0.0:{port}/?wsdl")
    server.serve_forever()