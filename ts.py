import logging, re, os, shutil, sys
from datetime import datetime
from collections import defaultdict
from os.path import expanduser

from dateutil.parser import parse as dateutil_parse
from modgrammar import *
import yaml

from invoice import Invoice


def get_default_settings():
    settings = {
        'billcode': False,
        'billrate': 1000.,
        'footer': [],
        'prefix': '',
        'invoice_on': 'marker',
        'invoice_marker': '====',
        'summary_on': 'marker',
        'summary_marker': '----',
        'verbose': 0,
        'weekly_summary_template': '----------       {hours_this_week} ({hours_since_invoice} uninvoiced)',
        'invoice_template': '==========       {hours_this_week} ({hours_since_invoice} since invoice)',
        'invoice_filename_template': 'invoice-{invoice_code}.pdf'
    }
    return settings

def samefile(f1, f2):
    '''
    A simple replacement of the os.path.samefile() function not existing
    on the Windows platform.
    MAC/Unix supported in standard way :).

    Author: Denis Barmenkov <denis.barmenkov@gmail.com>

    Source: code.activestate.com/recipes/576886/

    Copyright: this code is free, but if you want to use it, please
               keep this multiline comment along with function source.
               Thank you.

    2009-08-19 20:13
    '''
    try:
        return os.path.samefile(f1, f2)
    except AttributeError:
        f1 = os.path.abspath(f1).lower()
        f2 = os.path.abspath(f2).lower()
        return f1 == f2



logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

grammar_whitespace = False

class MyDate(Grammar):
    # grammar = (WORD('0-9', "-0-9/", grammar_name='date'))
    grammar = (WORD('2', "-0-9", fullmatch=True, grammar_name='date')
        | WORD('0-9', "-0-9/", grammar_name='date'))
    grammar_tags = ['date']

class BillCode(Grammar):
    """ All capital letter billing code. """
    grammar = (WORD("A-Z", grammar_name='bill_code'))

class Hours(Grammar):
    grammar = (WORD(".0-9", grammar_name='hours'), OPTIONAL("h"))

class Hour(Grammar):
    grammar = WORD("0-9", min=1, max=2, grammar_name='hour')

class Minute(Grammar):
    grammar = WORD("0-9", min=1, max=2, grammar_name='minute')

class AMPM(Grammar):
    grammar = L("A") | L("P") | L("a") | L("p")

class MyTime(Grammar):
    grammar = (G(Hour, OPTIONAL(":", Minute))), OPTIONAL(AMPM)
    # grammar = (WORD("0-9:", grammar_name='time'), OPTIONAL(L("A") | L("P") | L("a") | L("p"), grammar_name='ampm'))

class Range(Grammar):
    grammar = G(MyTime, OPTIONAL(SPACE), '-', OPTIONAL(SPACE),
        OPTIONAL(MyTime), OPTIONAL('(', Hours, ')'), grammar_name='range')

class RangeList(Grammar):
    grammar = LIST_OF(G(Range | Hours), sep=G(",", OPTIONAL(SPACE)), grammar_name="ranges")

class Prefix(Grammar):
    grammar = (ZERO_OR_MORE(L('*') | SPACE), )

class Suffix(Grammar):
    grammar = (OPTIONAL(SPACE), OPTIONAL(L('#'), REST_OF_LINE), EOF)

# 
class MyGrammar (Grammar):
    grammar = (
        G(Prefix, MyDate, SPACE, Hours, SPACE, RangeList, Suffix, grammar_name="3args") |
        G(Prefix, MyDate, SPACE, RangeList,  Suffix, grammar_name="2argrange") |
        G(Prefix, MyDate, SPACE, Hours, Suffix, grammar_name="2arghours") |
        G(Prefix, MyDate, SPACE, BillCode, SPACE, Hours, SPACE, RangeList, Suffix, grammar_name="3args") |
        G(Prefix, MyDate, SPACE, BillCode, SPACE, RangeList,  Suffix, grammar_name="2argrange") |
        G(Prefix, MyDate, SPACE, BillCode, SPACE, Hours, Suffix, grammar_name="2arghours") |
        G(Prefix, MyDate, Suffix, grammar_name="justdate")
    )

myparser = MyGrammar.parser()

time_regex = re.compile(r'(\d{1,2})(:\d+)?([aApP])?')
def parse_time(cur_date, time_str, after=None):
    """ Parse time

    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12p')
    datetime.datetime(2015, 6, 3, 12, 0)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12:01p')
    datetime.datetime(2015, 6, 3, 12, 1)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12a')
    datetime.datetime(2015, 6, 3, 0, 0)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '1')
    datetime.datetime(2015, 6, 3, 13, 0)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '1a')
    datetime.datetime(2015, 6, 3, 1, 0)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '11:45p')
    datetime.datetime(2015, 6, 3, 23, 45)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12:45a')
    datetime.datetime(2015, 6, 3, 0, 45)
    >>> parse_time(datetime(2015, 6, 3, 0, 0), '12:45p')
    datetime.datetime(2015, 6, 3, 12, 45)
    """

    m = time_regex.match(time_str)
    # print( "[parse_time]: " + time_str, m.groups())
    if not m:
        return None

    g = m.groups()
    # print(g)
    hour = int(g[0])
    minute = 0
    if g[1] is not None:
        minute = int(g[1][1:])

    if g[2] is not None:
        if hour != 12 and g[2] in ('p','P'):
            hour += 12
        elif hour == 12 and g[2] in ('a','A'):
            hour -= 12
    else:
        # AM/PM not specified.
        time_as_am_guess = datetime(cur_date.year, cur_date.month, cur_date.day, hour=hour, minute=minute)
        if after is not None:
            if after > time_as_am_guess:
                hour += 12
        else:
            if hour < 7:
                logger.warn("Assuming time {} is PM".format(time_str))
                hour += 12


    return datetime(cur_date.year, cur_date.month, cur_date.day, hour=hour, minute=minute)

class TimesheetParseError(Exception):
    pass

def parse(line, settings=None, prefix=None):
    """ Parse grammar.
    >>> myparser.parse_string("5/20/2015", reset=True, eof=True)
    MyGrammar<'5/20/2015'>
    >>> parse("5/20/2015", prefix='')
    {'date': datetime.date(2015, 5, 20), 'prefix': Prefix<''>, 'suffix': Suffix<None, None, ''>}
    >>> d = parse("6/21/2015 1.25  3:33-4:44a", prefix='')
    Traceback (most recent call last):
        ...
    TimesheetParseError: huh?
    >>> d = parse("5/20/2015 5  10:10 - 10:25a, 12-", prefix='')
    >>> d['date']
    datetime.date(2015, 5, 20)
    >>> d['hours']
    0.25
    >>> len(d['ranges'])
    2
    >>> d['ranges'][0]['s']
    datetime.datetime(2015, 5, 20, 10, 10)
    >>> format_ret(d)
    '2015-05-20   .25 10:10a-10:25a(.25), 12p-'
    >>> d = parse('6/15/2015 4.25  10a-11:30(1.5), 3-5:45p(2.75)', prefix='')
    >>> d['ranges'][1]['duration']
    2.75
    >>> d = parse('* 2015-06-03  1.5  10a-11:15a, 12:45p-1p, 6-6:15 # whatever yo', prefix='* ')
    >>> d = parse('* 7/22/2015 6.25  10:00a-11:30a(1.5), 12:30p-3:30p(3), 9:15p-11p(1.75)', prefix='* ')
    >>> d = parse('* 7/13/2015 3.5  .25, 1:30p-5p', prefix='* ')
    >>> format_ret(d)
    '* 2015-07-13  3.75 .25, 1:30p-5p(3.50)'
    """

    if settings is None:
        settings = get_default_settings()

    if prefix is None:
        prefix = settings.get('prefix','* ')

    if not line.strip():
        return None

    line = line.rstrip()
    origresult = myparser.parse_string(line, reset=True, eof=True) #, matchtype='longest')
    ret = {}
    result = origresult.elements[0]

    date_g = result.get(MyDate)
    if date_g is None:
        return None

    ret['prefix'] = result.get(Prefix)
    ret['suffix'] = result.get(Suffix)
    ret['billcode'] = result.get(BillCode)
    # ret['comment'] = ret['suffix'].get(Comment)

    cur_date = dateutil_parse(str(date_g)).date()
    ret['date'] = cur_date

    hours_g = result.get(Hours)
    if hours_g is not None:
        ret['hours'] = float(str(hours_g))

    ranges = result.get(RangeList)
    if ranges is not None:
        ret['ranges'] = []
        # logger.debug(ranges.elements)

        for r in ranges.elements[0].elements:
            if r.grammar_name == 'Hours':
                duration = float(str(r))
                ret['ranges'].append( {'duration': duration} )
            elif r.grammar_name == 'Range':
                times = r.find_all(MyTime)
                if len(times)==1:
                    start = str(times[0])
                    end = None
                elif len(times)==2:
                    start = str(times[0])
                    end = str(times[1])
                else:
                    raise Exception()

                try:
                    parsed_start = parse_time(cur_date, start)
                except (ValueError, ):
                    parsed_start = None


                parsed_end = None
                if end is not None:
                    try:
                        parsed_end = parse_time(cur_date, end, after=parsed_start)
                    except (ValueError, AttributeError):
                        pass

                if parsed_end is not None:
                    if parsed_end < parsed_start:
                        # import pdb; pdb.set_trace()
                        raise TimesheetParseError("{} < {} in {}".format(parsed_end, parsed_start, line))
                    duration = (parsed_end-parsed_start).seconds/60./60.
                else:
                    duration = None
                ret['ranges'].append( {'s': parsed_start, 'e': parsed_end, 'duration': duration} )
            else:
                pass


    if 'ranges' in ret:
        total_duration = sum([r['duration'] for r in ret['ranges'] if r['duration'] is not None])
        if 'hours' in ret and format_hours(total_duration) != format_hours(ret['hours']):
            logger.warn('Changing total hours from %s to %s\n  Original: %s' % (ret['hours'], total_duration, line))
        ret['hours'] = total_duration

        if len(ret['ranges']) == 1 and 's' not in ret['ranges'][0]:
            del ret['ranges']

    if 'hours' in ret and ret['hours'] > 9:
        logger.warn('Calculated duration={}, which is above normal\n  Original: {}'.format(ret['hours'], line))

    if settings['verbose'] >= 2:
        print('= parsed={}'.format(ret))

    return ret

def format_hours(h):
    if h is None:
        return '-'
    if int(h) == h:
        return str(int(h))

    return ("%.2f" % h).lstrip('0')

def format_time(t):
    """ Print out succinct time.
    >>> format_time(datetime(2015, 1, 1, 5, 15, 0))
    '5:15a'
    >>> format_time(datetime(2015, 1, 1, 12, 0, 0))
    '12p'
    >>> format_time(datetime(2015, 1, 1, 0, 1, 0))
    '12:01a'
    """
    if t is None:
        return ""

    ampm = "a"
    if t.hour > 12:
        ampm = "p"
        hour = t.hour - 12
    elif t.hour == 12:
        ampm = "p"
        hour = 12
    elif t.hour == 0:
        hour = 12
    else:
        hour = t.hour

    if t.minute==0:
        s = "%d%s" % (hour, ampm)
    else:
        s = "%d:%02d%s" % (hour, t.minute, ampm)
    return s

def format_range(r,):
    if 's' not in r:
        return '%s' % format_hours(r['duration'])
    else:
        if r['e'] is not None:
            return "%s-%s(%s)" % (format_time(r['s']), format_time(r['e']), format_hours(r['duration']))
        else:
            return "%s-" % (format_time(r['s']), )

def format_ret(ret, settings):
    formatted_billcode = ''
    if settings['billcode']:
        formatted_billcode = '%5s'% (ret.get('billcode', '') or '', )

    if 'ranges' not in ret:
        total_duration = ret['hours']
        output = '%10s%s %5s' % (ret['date'], formatted_billcode, format_hours(total_duration))
    else:
        parsed_ranges = ret['ranges']
        rearranges = [format_range(r) for r in parsed_ranges]
        output = '%10s%s %5s %s' % (ret['date'], formatted_billcode, format_hours(ret['hours']), ", ".join(rearranges))

    suffix = str(ret['suffix']).strip()
    if len(suffix) > 0:
        suffix = " " + suffix
    return '%s%s%s' % (ret['prefix'], output, suffix)


FRONT_MATTER_TERMINUS_REGEX = re.compile('^---+$')
def load_front_matter(f):
    """ Load jekyll-style front-matter config from top of file.

    >>> re.match
    datetime.datetime(2015, 6, 3, 12, 0)

    """
    settings = get_default_settings()

    def update_from_file(settings, filename):
        try:
            default_f = open(filename)
        except IOError:
            print "'{}' not found, skipping...".format(filename)
            return

        if default_f:
            print "loading from '{}'...".format(filename)
            default_yml_settings = yaml.load(default_f)
            settings.update(default_yml_settings)
            default_f.close()

    update_from_file(settings, expanduser('~/.tsconfig.yml'))
    update_from_file(settings, 'default.yml')

    front_matter = []
    found=False
    for line in f:
        if FRONT_MATTER_TERMINUS_REGEX.match(line):
            found=True
            break
        front_matter.append(line)

    if not found:
        print "Front-matter YAML is required."
        sys.exit(1)

    fm_settings = yaml.load("".join(front_matter))
    settings.update(fm_settings)

    return settings, front_matter


if __name__=='__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Process a timesheet')
    parser.add_argument('file', metavar='FILE')
    parser.add_argument('-v', '--verbose', action='count', default=None)
    parser.add_argument('-i', '--invoice', action='store_true', help='Write PDF invoice.')
    parser.add_argument('-o', '--out', default=None, help="Defaults to overwrite -f FILE.")

    args = parser.parse_args()

    if args.out is None:
        args.out = args.file

    input_filename = args.file
    output_filename = args.out
    if samefile(args.file, args.out):
        backup_filename = args.file + '.backup'
        shutil.copyfile(args.file, backup_filename)
        input_filename = backup_filename

    f = open(input_filename)

    summary_results = {}
    last_date = None
    last_iso = None

    invoice_has_started = False
    weekly_hours = 0.
    invoice_hours = 0.
    invoice_hours_per_code = defaultdict(int)

    def format_summary_line():
        # global weekly_hours, invoice_hours,
        weekly_summary_template = settings['prefix'] + settings['weekly_summary_template']
        return weekly_summary_template.format(
            hours_this_week=format_hours(weekly_hours),
            hours_since_invoice=format_hours(invoice_hours))

    def write_summary_line(invoice=False, original_line=''):
        global weekly_hours, invoice_hours
        if invoice:
            template = settings['invoice_template']
        else:
            template = settings['weekly_summary_template']

        summary_line = settings['prefix'] + template.format(
            hours_this_week=format_hours(weekly_hours),
            hours_since_invoice=format_hours(invoice_hours))

        original_line_split = original_line.split('#', 1)
        comment = ''
        if len(original_line_split)==2:
            comment = original_line_split[-1].strip()
            summary_line += ' # ' + comment

        invoice_id, invoice_description = '', ''
        try:
            invoice_id, invoice_description = comment.split(',', 1)
        except:
            pass

        if invoice:
            invoice_data = {'id': invoice_id, 'hours': invoice_hours, 'items': [], 'description': invoice_description.strip()}
            for k,v in invoice_hours_per_code.items():
                invoice_data['items'].append({'billcode': k, 'hours': v})
            invoices.append(invoice_data)

        if weekly_hours != 0. or invoice:
            if settings['verbose'] >= 1:
                print summary_line
            if outf:
                outf.write(summary_line + '\n')
            weekly_hours = 0.

            if invoice:
                invoice_hours = 0.
                invoice_hours_per_code.clear()

        if outf:
            outf.write('\n')



    settings, raw_front_matter = load_front_matter(f)
    if args.verbose is not None:
        settings['verbose'] = args.verbose

    # logger.info("settings {}".format(settings))

    outf = open(output_filename, 'w')

    for line in raw_front_matter:
        outf.write(line)

    # yaml.dump(settings, outf, default_flow_style=False)
    outf.write('----\n')

    invoices = []

    for line in f:
        if settings['verbose'] >= 1:
            print '< {}'.format(line.rstrip())

        try:
            if invoice_has_started:
                # Found an invoice marker, so rewrite it...
                if settings['invoice_on'] == 'marker' and line.startswith(settings['invoice_marker']):
                    write_summary_line(invoice=True, original_line=line)
                    if settings['verbose'] >= 1:
                        print "> Wrote summary line".format()
                    continue

                # Throw out empty lines
                if line.strip() == '':
                    continue

                # Just throw out old summary lines.. we'll write them again ourselves.
                if settings['summary_on'] == 'marker':
                    if line.startswith(settings['summary_marker']):
                        write_summary_line(original_line=line)
                        continue
                else:
                    if line.startswith(format_summary_line()):
                        continue

            ret = parse(line, settings)
            if ret is None:
                if settings['verbose'] >= 1 and line.strip() != '':
                    print "> Failed to parse. Writing straight.".format()
                if outf:
                    outf.write(line.rstrip() + '\n')
                continue

            if not invoice_has_started and settings['verbose'] >= 1:
                print "! Invoice has started!"
            invoice_has_started = True
            if last_date is not None and last_date > ret['date']:
                logger.warn('Date {} is listed after date {}.'.format(ret['date'], last_date))
            if ret['date'] in summary_results:
                logger.warn('Date {} listed multiple times.'.format(ret['date']))

            iso = ret['date'].isocalendar()
            if settings['summary_on'] == 'weekly':
                if last_iso is not None and (iso[0] != last_iso[0] or iso[1] != last_iso[1]):
                    write_summary_line()

            last_date = ret['date']
            last_iso = iso
            weekly_hours += ret['hours']
            invoice_hours += ret['hours']
            invoice_hours_per_code[str(ret.get('billcode', ''))] += ret['hours']

            summary_results[ret['date']] = ret

            fixed_line = format_ret(ret, settings)
            if settings['verbose'] >= 1:
                print ">", fixed_line
            if outf:
                outf.write(fixed_line.rstrip() + '\n')

        except TimesheetParseError:
            print "Problem parsing."
            raise
        except ParseError:
            if outf:
                outf.write(line.rstrip() + '\n')

            # print 'skipped...'
            pass
            # logger.exception("failed to parse")
            # raise
    write_summary_line()
    if outf:
        outf.close()

    print "{} hours uninvoiced currently...".format(format_hours(invoice_hours))

    if args.invoice:
        for i in invoices:
            invoice = Invoice(i['id'], [], settings['client_name'], footer=settings['footer'], body=[i['description']])
            for item in i['items']:
                billcode_data = settings['billcodes'][item['billcode']]
                invoice.add_item(
                    name=billcode_data['description'],
                    qty=round(item['hours'], 2),
                    unit_price=billcode_data['rate'],
                    description=billcode_data['description'])

            invoice_filename = invoice_filename_template.format(
                invoice_code=i['id'], 
                client_name=settings['client_name']
            )
            
            invoice.save(invoice_filename)
            print("Wrote invoice to {}".format(invoice_filename))
