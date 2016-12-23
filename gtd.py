'''Incremental development is a thing dude
TODOs:
- Option to work on a list other than "Inbound"
- "Daily review" mode where you review the active and blocked ones as well
'''
import re
import sys
import logging
import readline  # noqa
import datetime
import argparse

from trello import TrelloClient
import yaml


class Colors:
    esc = '\033'
    black = esc + '[0;30m'
    red = esc + '[0;31m'
    green = esc + '[0;32m'
    yellow = esc + '[0;33m'
    blue = esc + '[0;34m'
    purple = esc + '[0;35m'
    cyan = esc + '[0;36m'
    white = esc + '[0;37m'
    reset = esc + '[0m'


__version__ = '0.0.4'
__banner__ = '''Welcome to{1.green}

  __|_ _| ._
 (_||_(_|o|_)\/
  _|      |  /{1.red}

version {0}
by delucks{1.reset}
'''.format(__version__, Colors)


def parse_configuration(configfile='gtd.yaml'):
    '''load user-defined configuration for what boards and lists to use
    '''
    logging.info('Opening configuration file...')
    with open(configfile, 'r') as config_yaml:
        logging.info('Loading configuration properties...')
        return yaml.safe_load(config_yaml)


def initialize_trello(config):
    '''Initializes our connection to the trello API
    '''
    logging.info('Connecting to the Trello API...')
    trello_client = TrelloClient(
        api_key=config['trello']['api_key'],
        api_secret=config['trello']['api_secret'],
        token=config['trello']['oauth_token'],
        token_secret=config['trello']['oauth_token_secret']
    )
    logging.info('Connected to Trello.')
    return trello_client


def _filter_by_name(iterable, name):
    return [b for b in iterable if b.name == bytes(name, 'utf8')][0]


def _colorize(lbl, msg, colorstring=Colors.blue):
    return '  {0}{1}{2} {3}'.format(colorstring, lbl, Colors.reset, msg)


def display_card(card):
    created = card.create_date
    print('{1.red}Card {0}{1.reset}'.format(card.id, Colors))
    print(_colorize('Name:', card.name.decode('utf8')))
    print(_colorize('Created on:', '{0} ({1})'.format(created, created.timestamp())))
    print(_colorize('Age:', datetime.datetime.now(datetime.timezone.utc) - created))
    if card.labels:
        print(_colorize('Labels:', ','.join([l.name.decode('utf8') for l in card.labels])))
    if card.get_attachments():
        print(_colorize('Attachments:', ','.join([a['name'] for a in card.get_attachments()])))
    if card.due:
        diff = card.due_date - datetime.datetime.now(datetime.timezone.utc)
        if diff < datetime.timedelta(0):
            display = Colors.red
        else:
            display = Colors.green
        print(_colorize('Due:', card.due_date, display))
        print(_colorize('Remaining:', diff, display))


def prompt_for_user_choice(iterable):
    iterable = list(iterable)
    for index, item in enumerate(iterable):
        print('  [{0}] {1}'.format(index, item.decode('utf8')))
    broken = False
    while not broken:
        usersel = input('Input the numeric ID or IDs of the item(s) you want: ').strip()
        try:
            if ',' in usersel or ' ' in usersel:
                delimiter = ',' if ',' in usersel else ' '
                indicies = [int(i) for i in usersel.split(delimiter)]
            else:
                indicies = [int(usersel)]
            broken = True
        except ValueError:
            print('You gave a malformed input!')
    return [iterable[i] for i in indicies]


def prompt_for_confirmation(message, default=False):
    while True:
        choice = input(message).strip().lower()
        if choice == 'y' or choice == 'n' or choice == '':
            break
        else:
            print('Input was not y nor n, partner. Enter is OK if you meant to use the default')
    return choice == 'y' if choice != '' else default


def add_labels(card, lookup):
    if prompt_for_confirmation('Would you like to add labels? (y/N) '):
        done = False
        newlabels = []
        while not done:
            label_to_add = prompt_for_user_choice(lookup.keys())
            newlabels.extend([lookup[l] for l in label_to_add])
            done = prompt_for_confirmation('Are you done adding labels? (Y/n) ', default=True)
        return newlabels
    else:
        logging.info('User did not add labels')
        return False


def move_to_list(card, lookup, current):
    dest = prompt_for_user_choice(lookup.keys())[0]
    if lookup[dest].id == current.id:
        logging.info('Did not want to move')
        return False
    else:
        return lookup[dest]


def make_readable(object_grouping):
    return {o.name: o for o in object_grouping}


def apply_filters(cardlist, reverse=False, regex=None):
    cards = list(cardlist) 
    if regex:
        selected = [c for c in cardlist if re.search(regex, c.name.decode('utf8'))]
    else:
        selected = cards
    if reverse:
        return reversed(selected)
    else:
        return selected

def main():
    config_properties = parse_configuration()
    p = argparse.ArgumentParser(description='gtd.py version {0}'.format(__version__))
    p.add_argument('-r', '--reverse', help='process the list of cards in reverse', action='store_true')
    p.add_argument('-m', '--match', help='provide a regex to filter the card names on', default=None)
    p.add_argument('-l', '--list', help='inbound list name to use', default=config_properties['list_names']['incoming'])
    commands = p.add_subparsers(dest='command')
    show = commands.add_parser('show')
    show.add_argument('type', choices=('lists', 'cards'), default='lists')
    review = commands.add_parser('review')
    args = p.parse_args()

    trello = initialize_trello(config_properties)
    main_board = _filter_by_name(trello.list_boards(), config_properties['board_name'])
    inbound_list = _filter_by_name(main_board.get_lists('open'), args.list)
    cards = apply_filters(inbound_list.list_cards(), reverse=args.reverse, regex=args.match)

    print(__banner__)
    if args.command == 'show':
        if args.type == 'lists':
            for l in main_board.get_lists('open'):
                print(l.name.decode('utf8'))
            return True
        elif args.type == 'cards':
            for card in cards:
                display_card(card)
            return True
    else: # args.command == 'review':
        label_lookup = make_readable(main_board.get_labels())
        list_lookup = make_readable(main_board.get_lists('open'))
        for card in cards:
            display_card(card)
            keep = prompt_for_confirmation('Should we keep it? (Y/n) ', True)
            if keep:
                labels = add_labels(card, label_lookup)
                if labels:
                    for label in labels:
                        card.add_label(label)
                destination = move_to_list(card, list_lookup, inbound_list)
                if destination:
                    card.change_list(destination.id)
                    print('Moved to {0}'.format(destination.name.decode('utf8')))
                else:
                    print('Staying in inbound')
            else:
                card.delete()
        print('Good show, chap. Have a great day')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Quitting!')
        sys.exit(0)
