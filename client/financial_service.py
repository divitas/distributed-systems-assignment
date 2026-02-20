from flask import Flask, request, Response
import random

app = Flask(__name__)

WSDL = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             xmlns:tns="financial.transactions"
             targetNamespace="financial.transactions">
  <message name="PaymentRequest">
    <part name="name" type="xsd:string"/>
    <part name="card_number" type="xsd:string"/>
    <part name="expiration_date" type="xsd:string"/>
    <part name="security_code" type="xsd:string"/>
  </message>
  <message name="PaymentResponse">
    <part name="result" type="xsd:boolean"/>
  </message>
  <portType name="FinancialServicePortType">
    <operation name="ProcessPayment">
      <input message="tns:PaymentRequest"/>
      <output message="tns:PaymentResponse"/>
    </operation>
  </portType>
  <binding name="FinancialServiceBinding" type="tns:FinancialServicePortType">
    <soap:binding style="rpc" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="ProcessPayment">
      <soap:operation soapAction="ProcessPayment"/>
      <input><soap:body use="literal"/></input>
      <output><soap:body use="literal"/></output>
    </operation>
  </binding>
  <service name="FinancialService">
    <port name="FinancialServicePort" binding="tns:FinancialServiceBinding">
      <soap:address location="http://localhost:7000/"/>
    </port>
  </service>
</definitions>"""

@app.route('/', methods=['GET'])
def wsdl():
    return Response(WSDL, mimetype='text/xml')

@app.route('/', methods=['POST'])
def process():
    result = 'true' if random.random() < 0.9 else 'false'
    response_xml = f"""<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ProcessPaymentResponse>
      <result>{result}</result>
    </ProcessPaymentResponse>
  </soap:Body>
</soap:Envelope>"""
    return Response(response_xml, mimetype='text/xml')

if __name__ == '__main__':
    print("Financial SOAP service running on port 7000")
    app.run(host='0.0.0.0', port=7000)