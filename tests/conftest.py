"""Shared fixtures: minimal synthetic SEC XML documents (Form 4, 13F infoTable)."""

import pytest

FORM4_NS = "http://www.sec.gov/edgar/document/nvstg"

FORM4_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<unknownTag xmlns="{FORM4_NS}">
  <issuer>
    <issuerCik>0001326801</issuerCik>
    <issuerName>Test Issuer, Inc.</issuerName>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>DOE JANE Q</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>true</isOfficer>
      <officerTitle>Chief Financial Officer</officerTitle>
      <isTenPercentOwner>0</isTenPercentOwner>
      <isOther>false</isOther>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Class A Common Stock</value></securityTitle>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionDate><value>2026-09-28</value></transactionDate>
      <transactionShares><value>25000</value></transactionShares>
      <transactionPricePerShare><value>123.45</value></transactionPricePerShare>
      <transactionAquiredDisposedCode><value>D</value></transactionAquiredDisposedCode>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>100000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
      </ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeTransaction>
      <securityTitle><value>Option</value></securityTitle>
      <transactionShares><value>5000</value></transactionShares>
    </derivativeTransaction>
  </derivativeTable>
</unknownTag>
"""

# Same content, no namespace at all (filers vary)
FORM4_XML_NO_NS = FORM4_XML.replace(f' xmlns="{FORM4_NS}"', "")

THIRTEEN_F_XML = """<?xml version="1.0"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>ALLY FINL INC</nameOfIssuer>
    <titleOfClass>Com</titleOfClass>
    <cusip>02005N100</cusip>
    <value>577211815</value>
    <shrsOrPrnAmt><sshPrnamtType>SH</sshPrnamtType><sshPrnamt>12561737</sshPrnamt></shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority><Sole>12561737</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>TEST OPTION ISSUER</nameOfIssuer>
    <cusip>000000301</cusip>
    <value>9999</value>
    <shrsOrPrnAmt><sshPrnamtType>SH</sshPrnamtType><sshPrnamt>1000</sshPrnamt></shrsOrPrnAmt>
    <putCall>Put</putCall>
  </infoTable>
</informationTable>
"""


@pytest.fixture
def form4_xml():
    return FORM4_XML.encode()


@pytest.fixture
def form4_xml_no_ns():
    return FORM4_XML_NO_NS.encode()


@pytest.fixture
def form13f_xml():
    return THIRTEEN_F_XML.encode()


@pytest.fixture
def known_issuer(monkeypatch):
    """Force the issuer-name -> ticker resolver to succeed for scale tests."""
    monkeypatch.setattr("finresearch.form13f._name_to_ticker", lambda name: "TESTCO")
    return "TESTCO"
