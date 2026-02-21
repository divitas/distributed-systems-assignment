"""
Financial Transactions Service - Simple SOAP over HTTP
Runs on VM5, port 7000
"""

from flask import Flask, request, Response
import random

app = Flask(__name__)

@app.route('/', methods=['GET'])
def wsdl():
    wsdl = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             targetNamespace="financial.transactions">
  <message name="PaymentRequest"/>
  <message name="PaymentResponse"/>
  <portType name="FinancialServicePortType">
    <operation name="ProcessPayment">
      <input message="PaymentRequest"/>
      <output message="PaymentResponse"/>
    </operation>
  </portType>
  <binding name="FinancialServiceBinding" type="FinancialServicePortType">
    <soap:binding style="rpc" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="ProcessPayment">
      <soap:operation soapAction="ProcessPayment"/>
    </operation>
  </binding>
  <service name="FinancialService">
    <port name="FinancialServicePort" binding="FinancialServiceBinding">
      <soap:address location="http://0.0.0.0:7000/"/>
    </port>
  </service>
</definitions>"""
    return Response(wsdl, mimetype='text/xml')

@app.route('/', methods=['POST'])
def process():
    # 90% approval rate as per requirements
    result = 'true' if random.random() < 0.9 else 'false'
    response_xml = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ProcessPaymentResponse>
      <result>{}</result>
    </ProcessPaymentResponse>
  </soap:Body>
</soap:Envelope>""".format(result)
    return Response(response_xml, mimetype='text/xml')

if __name__ == '__main__':
    print("Financial SOAP service running on port 7000")
    app.run(host='0.0.0.0', port=7000)