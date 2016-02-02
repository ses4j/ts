# ts

**A text-based timesheet parser**  
*...because who has time to open Excel?*


This application is intended for use by contractors to track their hours in the
simplest, most programmer-friendly way possible; a human-friendly, 
computer-parseable text file format, one file per contract.  

A typical week's entry might look like this:

```
client_name: SuperCoolStartup LLC
----
2015-11-30  .25 # kickoff email
2015-12-01  10:45a-4:45p # began work on the website
---- # first week, woo!
2015-12-02  8:50a-10a, 12:15p-5:45p, 7:45p-9:30p # built testing fraamework
2015-12-03  10:09p-10:50p # respond to analysis document
2015-12-04  .50, 1:30p-2p, 3:20p-5:20p, 9:40-10:30
==== 
```

Some things to note:
* All timesheets begin with Jekyll-style "front matter" to configure invoice-specific settings.
* `----` tells the parser you want to summarize hours at this point.
* `====` tells the parser you want to invoice at this point, chronologically.
* Anything after a `#` is simply kept as a comment.

`ts` will parse and canonicalize this into:

```
client_name: SuperCoolStartup LLC
----

2015-11-30    .25 # kickoff email
2015-12-01      6 10:45a-4:45p(6) # began work on the website
----------   6.25 (6.25 uninvoiced) # first week, woo!
2015-12-02   8.42 8:50a-10a(1.17), 12:15p-5:45p(5.50), 7:45p-9:30p(1.75) # built testing fraamework
2015-12-03    .68 10:09p-10:50p(.68) # respond to analysis document
2015-12-04   3.83 .50, 1:30p-2p(.50), 3:20p-5:20p(2), 9:40p-10:30p(.83) 
==========  19.18 (26.68 since invoice)
```

## Global Configuration

User default configuration settings can go in ~/.tsconfig.yml (%USERPROFILE%\.tsconfig.yml on Windows).  

For instance: 
```
footer:
  - 'Please pay via bank transfer or check. All payments should be made in USD.'
  - 'Bank information for wire/direct deposit: My Bank, ABA/Routing: xxx, Acct#: yyy'
  - 'Make checks payable to XXX YYY'
invoice_filename_template: invoice-myname-{invoice_code}.pdf

# Here are some more.  These are the defaults, below, but uncomment if you want to change them.
# invoice_marker: ====
# invoice_on: marker
# invoice_template: ==========       {hours_this_week} ({hours_since_invoice} since
  invoice)
# prefix: ''
# summary_marker: '----'
# summary_on: marker
# verbose: 0
# weekly_summary_template: '----------       {hours_this_week} ({hours_since_invoice}
  uninvoiced)'
```

## Generating Invoices

To generate a PDF invoice, include an invoice marker in the file where you want it 
and then use the `-i/--invoice` option.  It will write one PDF for every `invoice_marker` 
(`====` by default) it finds, and include the comment in the invoice.  For example:
```
====  # MYCLIENT001, This invoice covers everything through Jan 31, 2016.
```

A file (using the `invoice_filename_template` setting) will be generated.  The template supports `{invoice_code}`, which comes from the ==== comment before the first comma.

Easy!

## TODO

* pyinstaller http://www.pyinstaller.org/ to build executable
* pdf/html/txt export?  https://github.com/xhtml2pdf/xhtml2pdf?
* cloud storage?