#!/usr/bin/env python

import argparse
import requests
import os
import re
import sys
import tarfile

LOOP = (
    'except-interface',
    'interface',
    'listen-address',
    'no-dhcp-interface',
)

LOOP_INLINE = (
    '',
)

NEEDS_QUOTE = (
    'alias',
    'cname',
    'conf-file',
    'dhcp-boot',
    'dhcp-host',
    'dhcp-ignore',
    'dhcp-option',
    'dhcp-option-force',
    'dhcp-userclass',
    'dhcp-vendorclass',
    'ptr-record',
    'pxe-prompt',
    'srv-host',
    'txt-record',
)

DEFAULTS = {
    'user': 'dnszasq',
    'group': 'dnsmasq',
}

parser = argparse.ArgumentParser(description='Generate a Jinja2 template from dnsmasq config file')
parser.add_argument('--version', type=str, help='dnsmasq version to fetch config for', default='2.79')
parser.add_argument('--prefix', type=str, help='prefix added to each variable', default='dnsmasq_')
parser.add_argument('--filename', type=str, help='file to extract', default='dnsmasq.conf.example')

args = parser.parse_args()

# Get URL
os.chdir(os.path.abspath(os.path.dirname(sys.argv[0])))
filename = 'dnsmasq-{version}.tar.gz'.format(version=args.version)
if os.path.isfile(filename):
    print('Files {filename} already exists. Skipping download'.format(filename=filename))
else:
    url = 'http://www.thekelleys.org.uk/dnsmasq/{filename}'.format(filename=filename)
    req = requests.get(url)

    if req.status_code != 200:
        sys.exit('Failed to download {0}'.format(filename))
    with open(filename, 'wb') as file:
        file.write(req.content)

# Unarchive config file from URL
with tarfile.open(filename, 'r') as tgz:
    members = tgz.getnames()
    conffile = [f for f in members if args.filename in f][0]
    tgz.extract(conffile, path='.')

# Parse config file
with open(conffile, 'r') as cf:
    lines = cf.readlines()
    lines.sort()

output_dir = 'output-{version}'.format(version=args.version)
if not os.path.isdir(output_dir):
    os.mkdir(output_dir)


# Write out defaults/main.yml, table of vars for README, and a Jinja template file
param_re = re.compile('^#([\w-]+)=?(.*?)(?: #.*)?$')
skip_re = re.compile('#Example')
template_file = '{output_dir}/dnsmasq.conf.j2'.format(output_dir=output_dir)
defaults_file = '{output_dir}/defaults_main.yml'.format(output_dir=output_dir)
readme_file = '{output_dir}/README.md'.format(output_dir=output_dir)

with open(template_file, 'w') as template, \
     open(readme_file, 'w') as readme, \
     open(defaults_file, 'w') as defaults:

    written_params = []
    table_line = '| `{prefix}{var_param}` | `{value}` |  |\n'
    default_line_quoted = "{prefix}{var_param}: '{value}'\n"
    template_loop_end = '{% endfor %}\n'

    readme.write('# Dnsmasq #\n\n'
                 '| Name              | Default Value       | Description          |\n'
                 '|-------------------|---------------------|----------------------|\n')

    template.write('# {{ ansible_managed }}\n')

    for line in lines:

        default_line = '{prefix}{var_param}: {value}\n'
        default_line_bool = '{prefix}{var_param}: true\n'
        template_conditional = '{{% if {prefix}{var_param} is defined %}}\n'
        template_loop_start = ''
        template_line = '{orig_param}={{{{ {prefix}{var_param} }}}}\n'
        template_line_bool = '{{{{ {prefix}{var_param} }}}}\n'

        if skip_re.match(line):
            continue

        param_match = param_re.match(line)
        if param_match:
            # Keep the original parameter name and make a copy with underscores
            # instead of dashes
            orig_param = param_match.groups()[0]
            var_param = param_match.groups()[0].replace('-', '_')

            # Only process the option once even if it occurs multiples times in the example config
            if orig_param not in written_params:
                written_params.append(orig_param)

                # Put in my own default values rather than what is found in the example config
                if orig_param in DEFAULTS.keys():
                    value = DEFAULTS[orig_param]
                else:
                    value = param_match.groups()[1]

                # Parameters that I want to pass in as a list and generate one line per item
                if orig_param in LOOP:
                    var_param = '{0}s'.format(var_param)
                    value = '[]'
                    template_conditional = ''
                    template_loop_start = '{{% for item in {prefix}{var_param} %}}\n'
                    template_line = '{orig_param}={{{{ item }}}}\n'

                # If there isn't a value of = on the line, assume it's a boolean value and default to 'false'
                elif not param_match.groups()[1]:
                    template_conditional = '{{% if {prefix}{var_param} %}}\n'
                    template_line = template_line_bool
                    value = 'false'

                # Quote the line if it contains values that are problematic for YAML
                if orig_param in NEEDS_QUOTE:
                    default_line = default_line_quoted

                # Write out the template, defaults/main.yml, and README files
                if template_conditional:
                    template.write(template_conditional.format(prefix=args.prefix, var_param=var_param))
                if template_loop_start:
                    template.write(template_loop_start.format(prefix=args.prefix, var_param=var_param))
                template.write(template_line.format(prefix=args.prefix, orig_param=orig_param, var_param=var_param))
                defaults.write(default_line.format(prefix=args.prefix, var_param=var_param, value=value))
                readme.write(table_line.format(prefix=args.prefix, var_param=var_param, value=value))
                if template_loop_start:
                    template.write(template_loop_end)
                if template_conditional:
                    template.write('{{% endif %}}\n')
