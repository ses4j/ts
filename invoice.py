import datetime
import logging, re, os, shutil, sys
import locale

from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

def generate_invoice():
    p = canvas.Canvas("out.pdf")
    p.drawString(100, 100, "Hello world.")
    p.showPage()
    p.save()

from reportlab.lib.units import cm
# from invoice.conf import settings
import importlib

consultant_logo_filename = None
business_details = (
    'Scott Stafford',
    '1212 Mockingbird Lane',
    'City, ST  11111',
    '',
    'Email: scott.stafford@example.com',
)

note = (
    'PAYMENT TERMS: 30 DAYS FROM INVOICE DATE.',
    'Please make all cheques payable to Your Name.',
)

locale.setlocale( locale.LC_ALL, '' )

def format_currency(value, currency):
    return locale.currency(value, grouping=True) #"{0:C0}".format(value)

def draw_header(canvas):
    """ Draws the invoice header """
    canvas.setStrokeColorRGB(176/255., 196/255., 222/255.)
    # canvas.setStrokeColorRGB(0.9, 0.5, 0.2)
    canvas.setFillColorRGB(0.2, 0.2, 0.2)
    canvas.setFont('Helvetica', 16)
    canvas.drawString(18 * cm, -1 * cm, 'Invoice')
    if consultant_logo_filename:
        canvas.drawInlineImage(consultant_logo_filename, 1 * cm, -1 * cm, 250, 16)
    canvas.setLineWidth(4)
    canvas.line(0, -1.25 * cm, 21.7 * cm, -1.25 * cm)


def draw_address(canvas):
    """ Draws the business address """

    canvas.setFont('Helvetica', 9)
    textobject = canvas.beginText(13 * cm, -2.5 * cm)
    for line in business_details:
        textobject.textLine(line)
    canvas.drawText(textobject)


def draw_footer(canvas, text=None):
    """ Draws the invoice footer """
    note = (
        'Bank Details: Street address, Town, County, POSTCODE',
        'Sort Code: 00-00-00 Account No: 00000000 (Quote invoice number).',
        'Please pay via bank transfer or cheque. All payments should be made in CURRENCY.',
        'Make cheques payable to Company Name Ltd.',
    )
    if text is None:
        text = note
    textobject = canvas.beginText(1 * cm, -27 * cm)
    for line in text:
        textobject.textLine(line)
    canvas.drawText(textobject)


# inv_module = importlib.import_module(settings.INV_MODULE)
# header_func = inv_module.draw_header
# address_func = inv_module.draw_address
# footer_func = inv_module.draw_footer
header_func = draw_header
address_func = draw_address
footer_func = draw_footer


def draw_pdf(buffer, invoice):
    """ Draws the invoice """
    canvas = Canvas(buffer, pagesize=A4)
    canvas.translate(0, 29.7 * cm)
    canvas.setFont('Helvetica', 10)

    canvas.saveState()
    header_func(canvas)
    canvas.restoreState()

    canvas.saveState()
    footer_func(canvas, invoice.footer)
    canvas.restoreState()

    canvas.saveState()
    address_func(canvas)
    canvas.restoreState()

    # Client address
    textobject = canvas.beginText(1.5 * cm, -2.5 * cm)
    for line in invoice.client_business_details:
        textobject.textLine(line)

    # if invoice.address.contact_name:
    #     textobject.textLine(invoice.address.contact_name)
    # textobject.textLine(invoice.address.address_one)
    # if invoice.address.address_two:
    #     textobject.textLine(invoice.address.address_two)
    # textobject.textLine(invoice.address.town)
    # if invoice.address.county:
    #     textobject.textLine(invoice.address.county)
    # textobject.textLine(invoice.address.postcode)
    # textobject.textLine(invoice.address.country.name)
    canvas.drawText(textobject)

    # Info
    textobject = canvas.beginText(1.5 * cm, -6.75 * cm)
    textobject.textLine('Invoice ID: %s' % invoice.invoice_id)
    textobject.textLine('Invoice Date: %s' % invoice.invoice_date.strftime('%d %b %Y'))
    textobject.textLine('Client: %s' % invoice.client)

    for line in invoice.body_text:
        textobject.textLine(line)

    canvas.drawText(textobject)

    # Items
    data = [['Quantity', 'Description', 'Amount', 'Total'], ]
    for item in invoice.items:
        data.append([
            item.quantity,
            item.description,
            format_currency(item.unit_price, invoice.currency),
            format_currency(item.total(), invoice.currency)
        ])
    data.append(['', '', 'Total:', format_currency(invoice.total(), invoice.currency)])
    table = Table(data, colWidths=[2 * cm, 11 * cm, 3 * cm, 3 * cm])
    table.setStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), (0.2, 0.2, 0.2)),
        ('GRID', (0, 0), (-1, -2), 1, (0.7, 0.7, 0.7)),
        ('GRID', (-2, -1), (-1, -1), 1, (0.7, 0.7, 0.7)),
        ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 0), (-1, 0), (0.8, 0.8, 0.8)),
    ])
    tw, th, = table.wrapOn(canvas, 15 * cm, 19 * cm)
    table.drawOn(canvas, 1 * cm, -10 * cm - th)

    canvas.showPage()
    canvas.save()

class Invoice():
    def __init__(self, id, client_business_details, client_name,
        invoice_date=datetime.datetime.now(),
        currency='USD', body=None, footer=None):
        self.invoice_id = id
        self.invoice_date = invoice_date
        self.client = client_name
        self.currency = currency
        self.items = []
        self.client_business_details = client_business_details
        self.footer = footer
        self.body_text = body

    def total(self):
        return sum([i.total() for i in self.items])

    def add_item(self, *args, **kwargs):
        self.items.append(Item(*args, **kwargs))

    def save(self, out_filepath):
        if out_filepath.lower().endswith('.pdf'):
            draw_pdf(out_filepath, self)
        else:
            raise NotImplementedError("only .pdf")


class Item(object):
    def __init__(self, name, qty, unit_price, description = ''):
        self.name = name
        self.description = description
        self.quantity = qty
        self.unit_price = unit_price

    def total(self):
        return self.unit_price * self.quantity

class Country():
    def __init__(self, name):
        self.name = name

# class Address():
#     def __init__(self, name, address_one=None, address_two=None):
#         self.contact_name = name
#         self.address_one = address_one
#         self.address_two = address_two
#         self.town = name
#         self.county = name
#         self.postcode = name
#         self.country = Country(name)

# address = Address('Vestorly', "NYC")
client_business_details = [
    'Vestorly',
    'NYC',
]

if __name__=='__main__':
    invoice = Invoice("VES001", client_business_details, "Vestorly")
    invoice.add_item(Item('august hours', 50.25, 125.0, 'Hours for august'))
    draw_pdf('out.pdf', invoice)