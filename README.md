# ts
Text-based timesheet parser

This application is intended for use by contractors to track their hours in the
simplest, most programmer-friendly way possible -- a human-friendly, 
computer-parseable text file format, one file per contract.  A typical week's
entry might look like this:

```
2015-11-30  .25 # kickoff email
2015-12-01  10:45a-4:45p # began work on the website
----
2015-12-02  8:50a-10a, 12:15p-5:45p, 7:45p-9:30p # built testing fraamework
2015-12-03  10:09p-10:50p # respond to analysis document
2015-12-04  .50, 1:30p-2p, 3:20p-5:20p, 9:40-10:30
==== 
```

* ---- tells the parser you want to summarize hours at this point.
* ==== tells the parser you want to invoice at this point, chronologically.

`ts` will parse and canonicalize this into:

```
2015-11-30    .25 # kickoff email
2015-12-01      6 10:45a-4:45p(6) # began work on the website
----------   6.25 (6.25 uninvoiced)
2015-12-02   8.42 8:50a-10a(1.17), 12:15p-5:45p(5.50), 7:45p-9:30p(1.75) # built testing fraamework
2015-12-03    .68 10:09p-10:50p(.68) # respond to analysis document
2015-12-04   3.83 .50, 1:30p-2p(.50), 3:20p-5:20p(2), 9:40p-10:30p(.83) 
==========  19.18 (26.68 since invoice)
```

Easy!