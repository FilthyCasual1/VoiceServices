"""Cisco XML rendering, independent of CUCM provisioning and CTI."""
from urllib.parse import urlencode
from xml.etree.ElementTree import Element, SubElement, tostring


def field(parent, name, value):
    SubElement(parent, name).text = str(value)


def xml(root):
    return tostring(root, encoding='utf-8', xml_declaration=True)


def text(title, message):
    root = Element('CiscoIPPhoneText')
    field(root, 'Title', title)
    field(root, 'Prompt', 'VoiceServices')
    field(root, 'Text', message)
    return xml(root)


def menu(base, token):
    root = Element('CiscoIPPhoneMenu')
    field(root, 'Title', 'VoiceServices')
    field(root, 'Prompt', 'Select an application')
    for label, route in [('Directory','directory'), ('Calculator','calculator'), ('Weather','weather'),
                         ('RSS feeds','rss'), ('Flight tracker','flights'), ('Recordings','recordings'),
                         ('Network status','network'), ('Save current number','current-number')]:
        item = SubElement(root, 'MenuItem')
        field(item, 'Name', label)
        field(item, 'URL', base+'/phone/'+route+'?'+urlencode({'token':token}))
    return xml(root)


def calculator(base, token):
    root = Element('CiscoIPPhoneInput')
    field(root, 'Title', 'Calculator')
    field(root, 'Prompt', 'Operation: add/subtract/multiply/divide')
    field(root, 'URL', base+'/phone/calculate?'+urlencode({'token':token}))
    for label, param, default, flags in [('First number','left','0','A'),
                                        ('Operation','operation','add','A'),
                                        ('Second number','right','0','A')]:
        item = SubElement(root, 'InputItem')
        for tag, value in [('DisplayName',label), ('QueryStringParam',param),
                           ('DefaultValue',default), ('InputFlags',flags)]:
            field(item, tag, value)
    return xml(root)


def directory(contacts):
    root = Element('CiscoIPPhoneDirectory')
    field(root, 'Title', 'Directory')
    field(root, 'Prompt', 'Select a contact to dial')
    for contact in contacts:
        item = SubElement(root, 'DirectoryEntry')
        field(item, 'Name', contact['name'])
        field(item, 'Telephone', contact['number'])
    return xml(root)
