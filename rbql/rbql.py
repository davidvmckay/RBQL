#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function

import sys
import os
import re
import importlib
import codecs
import io
import tempfile
import random
import shutil
import time

##########################################################################
#
# RBQL: RainBow Query Language
# Authors: Dmitry Ignatovich, ...
#
#
##########################################################################

# This module must be both python2 and python3 compatible


# FIXME the main problem is the outermost rbql interface. Currently it provides 2 funtions that has to be called one after the other. Can we do better? Merge them into a single one.
# TODO rename STRICT_LEFT_JOIN -> STRICT_JOIN


__version__ = '0.5.0'


GROUP_BY = 'GROUP BY'
UPDATE = 'UPDATE'
SELECT = 'SELECT'
JOIN = 'JOIN'
INNER_JOIN = 'INNER JOIN'
LEFT_JOIN = 'LEFT JOIN'
STRICT_LEFT_JOIN = 'STRICT LEFT JOIN'
ORDER_BY = 'ORDER BY'
WHERE = 'WHERE'
LIMIT = 'LIMIT'
EXCEPT = 'EXCEPT'


default_csv_encoding = 'latin-1'

PY3 = sys.version_info[0] == 3

rbql_home_dir = os.path.dirname(os.path.abspath(__file__))
user_home_dir = os.path.expanduser('~')
table_names_settings_path = os.path.join(user_home_dir, '.rbql_table_names')
table_index_path = os.path.join(user_home_dir, '.rbql_table_index')
default_init_source_path = os.path.join(user_home_dir, '.rbql_init_source.py')

py_script_body = codecs.open(os.path.join(rbql_home_dir, 'template.py'), encoding='utf-8').read()


class RbqlError(Exception):
    pass


def normalize_delim(delim):
    if delim == 'TAB':
        return '\t'
    if delim == r'\t':
        return '\t'
    return delim


def get_encoded_stdin(encoding_name):
    if PY3:
        return io.TextIOWrapper(sys.stdin.buffer, encoding=encoding_name)
    else:
        return codecs.getreader(encoding_name)(sys.stdin)


def get_encoded_stdout(encoding_name):
    if PY3:
        return io.TextIOWrapper(sys.stdout.buffer, encoding=encoding_name)
    else:
        return codecs.getwriter(encoding_name)(sys.stdout)


def xrange6(x):
    if PY3:
        return range(x)
    return xrange(x)


def rbql_meta_format(template_src, meta_params):
    for key, value in meta_params.items():
        # TODO make special replace for multiple statements, like in update, it should be indent-aware. values should be a list in this case to avoid join/split
        template_src_upd = template_src.replace(key, value)
        assert template_src_upd != template_src
        template_src = template_src_upd
    return template_src


def remove_if_possible(file_path):
    try:
        os.remove(file_path)
    except Exception:
        pass


class RBParsingError(Exception):
    pass


def strip_py_comments(cline):
    cline = cline.strip()
    if cline.startswith('#'):
        return ''
    return cline


def escape_string_literal(src):
    result = src.replace('\\', '\\\\')
    result = result.replace('\t', '\\t')
    result = result.replace("'", r"\'")
    return result


def parse_join_expression(src):
    match = re.match(r'(?i)^ *([^ ]+) +on +([ab][0-9]+) *== *([ab][0-9]+) *$', src)
    if match is None:
        raise RBParsingError('Invalid join syntax. Must be: "<JOIN> /path/to/B/table on a<i> == b<j>"')
    table_id = match.group(1)
    avar = match.group(2)
    bvar = match.group(3)
    if avar[0] == 'b':
        avar, bvar = bvar, avar
    if avar[0] != 'a' or bvar[0] != 'b':
        raise RBParsingError('Invalid join syntax. Must be: "<JOIN> /path/to/B/table on a<i> == b<j>"')
    lhs_join_var = 'safe_join_get(afields, {})'.format(int(avar[1:]))
    rhs_key_index = int(bvar[1:]) - 1
    return (table_id, lhs_join_var, rhs_key_index)


def generate_init_statements(column_vars, indent):
    init_statements = []
    for var_name in column_vars:
        var_group = var_name[0]
        one_based_idx = int(var_name[1:])
        if var_group == 'a':
            init_statements.append('{} = safe_get(afields, {})'.format(var_name, one_based_idx))
        if var_group == 'b':
            init_statements.append('{} = safe_get(bfields, {}) if bfields is not None else None'.format(var_name, one_based_idx))
    for i in range(1, len(init_statements)):
        init_statements[i] = indent + init_statements[i]
    result = '\n'.join(init_statements)
    return result



def replace_star_count(aggregate_expression):
    return re.sub(r'(^|(?<=,)) *COUNT\( *\* *\) *($|(?=,))', ' COUNT(1)', aggregate_expression).lstrip(' ')


def replace_star_vars_py(rbql_expression):
    rbql_expression = re.sub(r'(?:^|,) *\* *(?=, *\* *($|,))', '] + star_fields + [', rbql_expression)
    rbql_expression = re.sub(r'(?:^|,) *\* *(?:$|,)', '] + star_fields + [', rbql_expression)
    return rbql_expression


def translate_update_expression(update_expression, indent):
    translated = re.sub('(?:^|,) *a([1-9][0-9]*) *=(?=[^=])', '\nsafe_set(up_fields, \\1,', update_expression)
    update_statements = translated.split('\n')
    update_statements = [s.strip() for s in update_statements]
    if len(update_statements) < 2 or update_statements[0] != '':
        raise RBParsingError('Unable to parse "UPDATE" expression')
    update_statements = update_statements[1:]
    update_statements = ['{})'.format(s) for s in update_statements]
    for i in range(1, len(update_statements)):
        update_statements[i] = indent + update_statements[i]
    translated = '\n'.join(update_statements)
    return translated


def translate_select_expression_py(select_expression):
    translated = replace_star_count(select_expression)
    translated = replace_star_vars_py(translated)
    translated = translated.strip()
    if not len(translated):
        raise RBParsingError('"SELECT" expression is empty')
    return '[{}]'.format(translated)


def separate_string_literals_py(rbql_expression):
    string_literals_regex = r'''(\"\"\"|\'\'\'|\"|\')((?<!\\)(\\\\)*\\\1|.)*?\1'''
    return do_separate_string_literals(rbql_expression, string_literals_regex)


def do_separate_string_literals(rbql_expression, string_literals_regex):
    # The regex is improved expression from here: https://stackoverflow.com/a/14366904/2898283
    matches = list(re.finditer(string_literals_regex, rbql_expression))
    string_literals = list()
    format_parts = list()
    idx_before = 0
    for m in matches:
        literal_id = len(string_literals)
        string_literals.append(m.group(0))
        format_parts.append(rbql_expression[idx_before:m.start()])
        format_parts.append('###RBQL_STRING_LITERAL###{}'.format(literal_id))
        idx_before = m.end()
    format_parts.append(rbql_expression[idx_before:])
    format_expression = ''.join(format_parts)
    format_expression = format_expression.replace('\t', ' ')
    return (format_expression, string_literals)


def combine_string_literals(backend_expression, string_literals):
    for i in range(len(string_literals)):
        backend_expression = backend_expression.replace('###RBQL_STRING_LITERAL###{}'.format(i), string_literals[i])
    return backend_expression


def locate_statements(rbql_expression):
    statement_groups = list()
    statement_groups.append([STRICT_LEFT_JOIN, LEFT_JOIN, INNER_JOIN, JOIN])
    statement_groups.append([SELECT])
    statement_groups.append([ORDER_BY])
    statement_groups.append([WHERE])
    statement_groups.append([UPDATE])
    statement_groups.append([GROUP_BY])
    statement_groups.append([LIMIT])
    statement_groups.append([EXCEPT])

    result = list()
    for st_group in statement_groups:
        for statement in st_group:
            rgxp = r'(?i)(?:^| ){}(?= )'.format(statement.replace(' ', ' *'))
            matches = list(re.finditer(rgxp, rbql_expression))
            if not len(matches):
                continue
            if len(matches) > 1:
                raise RBParsingError('More than one "{}" statements found'.format(statement))
            assert len(matches) == 1
            match = matches[0]
            result.append((match.start(), match.end(), statement))
            break # Break to avoid matching a sub-statement from the same group e.g. "INNER JOIN" -> "JOIN"
    return sorted(result)


def separate_actions(rbql_expression):
    # TODO add more checks: 
    # make sure all rbql_expression was separated and SELECT or UPDATE is at the beginning
    rbql_expression = rbql_expression.strip(' ')
    ordered_statements = locate_statements(rbql_expression)
    result = dict()
    for i in range(len(ordered_statements)):
        statement_start = ordered_statements[i][0]
        span_start = ordered_statements[i][1]
        statement = ordered_statements[i][2]
        span_end = ordered_statements[i + 1][0] if i + 1 < len(ordered_statements) else len(rbql_expression)
        assert statement_start < span_start
        assert span_start <= span_end
        span = rbql_expression[span_start:span_end]

        statement_params = dict()

        if statement in [STRICT_LEFT_JOIN, LEFT_JOIN, INNER_JOIN, JOIN]:
            statement_params['join_subtype'] = statement
            statement = JOIN

        if statement == UPDATE:
            if statement_start != 0:
                raise RBParsingError('UPDATE keyword must be at the beginning of the query')
            span = re.sub('(?i)^ *SET ', '', span)

        if statement == ORDER_BY:
            span = re.sub('(?i) ASC *$', '', span)
            new_span = re.sub('(?i) DESC *$', '', span)
            if new_span != span:
                span = new_span
                statement_params['reverse'] = True
            else:
                statement_params['reverse'] = False

        if statement == SELECT:
            if statement_start != 0:
                raise RBParsingError('SELECT keyword must be at the beginning of the query')
            match = re.match('(?i)^ *TOP *([0-9]+) ', span)
            if match is not None:
                statement_params['top'] = int(match.group(1))
                span = span[match.end():]
            match = re.match('(?i)^ *DISTINCT *(COUNT)? ', span)
            if match is not None:
                statement_params['distinct'] = True
                if match.group(1) is not None:
                    statement_params['distinct_count'] = True
                span = span[match.end():]

        statement_params['text'] = span.strip()
        result[statement] = statement_params
    if SELECT not in result and UPDATE not in result:
        raise RBParsingError('Query must contain either SELECT or UPDATE statement')
    assert (SELECT in result) != (UPDATE in result)
    return result


def find_top(rb_actions):
    if LIMIT in rb_actions:
        try:
            return int(rb_actions[LIMIT]['text'])
        except ValueError:
            raise RBParsingError('LIMIT keyword must be followed by an integer')
    return rb_actions[SELECT].get('top', None)


def make_user_init_code(rbql_init_source_path):
    source_lines = None
    with open(rbql_init_source_path) as src:
        source_lines = src.readlines()
    source_lines = ['    ' + l.rstrip() for l in source_lines]
    return '\n'.join(source_lines) + '\n'


def extract_column_vars(rbql_expression):
    rgx = '(?:^|[^_a-zA-Z0-9])([ab][1-9][0-9]*)(?:$|(?=[^_a-zA-Z0-9]))'
    matches = list(re.finditer(rgx, rbql_expression))
    return list(set([m.group(1) for m in matches]))


def translate_except_expression(except_expression):
    skip_vars = except_expression.split(',')
    skip_vars = [v.strip() for v in skip_vars]
    skip_indices = list()
    for var_name in skip_vars:
        if re.match('^a[1-9][0-9]*$', var_name) is None:
            raise RBParsingError('Invalid EXCEPT syntax')
        skip_indices.append(int(var_name[1:]) - 1)
    skip_indices = sorted(skip_indices)
    skip_indices = [str(v) for v in skip_indices]
    return 'select_except(afields, [{}])'.format(','.join(skip_indices))


def is_ascii(s):
    return all(ord(c) < 128 for c in s)


def make_inconsistent_num_fields_hr_warning(table_name, inconsistent_records_info):
    assert len(inconsistent_records_info) > 1
    inconsistent_records_info = inconsistent_records_info.items()
    inconsistent_records_info = sorted(inconsistent_records_info, key=lambda v: v[1])
    num_fields_1, record_num_1 = inconsistent_records_info[0]
    num_fields_2, record_num_2 = inconsistent_records_info[1]
    warn_msg = 'Number of fields in "{}" table is not consistent: '.format(table_name)
    warn_msg += 'e.g. record {} -> {} fields, record {} -> {} fields'.format(record_num_1, num_fields_1, record_num_2, num_fields_2)
    return warn_msg


class HashJoinMap:
    # Other possible flavors: BinarySearchJoinMap, MergeJoinMap
    def __init__(self, record_iterator, key_index):
        self.max_record_len = 0
        self.hash_map = defaultdict(list)
        self.record_iterator = record_iterator
        self.key_index = key_index
        self.fields_info = dict()


    def build(self):
        nr = 0
        while True:
            fields = self.record_iterator.get_record()
            if fields is None:
                break
            nr += 1
            num_fields = len(fields)
            if num_fields not in self.fields_info:
                self.fields_info[num_fields] = nr
            self.max_record_len = max(self.max_record_len, num_fields)
            if self.key_index >= num_fields:
                raise RbqlError('No "b' + str(self.key_index + 1) + '" field at record: ' + str(nr) + ' in "B" table')
            self.hash_map.append(fields)


    def get_join_records(self, key):
        return self.hash_map.get(key)


    def get_warnings(self):
        warnings = []
        if len(self.fields_info) > 1:
            warnings.append(make_inconsistent_num_fields_hr_warning(self.fields_info))
        warnings += self.record_iterator.get_warnings()
        return warnings



def parse_to_py(query, join_tables_registry, user_init_code):
    rbql_lines = query.split('\n')
    rbql_lines = [strip_py_comments(l) for l in rbql_lines]
    rbql_lines = [l for l in rbql_lines if len(l)]
    full_rbql_expression = ' '.join(rbql_lines)
    column_vars = extract_column_vars(full_rbql_expression)
    format_expression, string_literals = separate_string_literals_py(full_rbql_expression)
    rb_actions = separate_actions(format_expression)

    py_meta_params = dict()
    py_meta_params['__RBQLMP__user_init_code'] = user_init_code

    if ORDER_BY in rb_actions and UPDATE in rb_actions:
        raise RBParsingError('"ORDER BY" is not allowed in "UPDATE" queries')

    if GROUP_BY in rb_actions:
        if ORDER_BY in rb_actions or UPDATE in rb_actions:
            raise RBParsingError('"ORDER BY" and "UPDATE" are not allowed in aggregate queries')
        aggregation_key_expression = rb_actions[GROUP_BY]['text']
        py_meta_params['__RBQLMP__aggregation_key_expression'] = '({},)'.format(combine_string_literals(aggregation_key_expression, string_literals))
    else:
        py_meta_params['__RBQLMP__aggregation_key_expression'] = 'None'

    join_map = None
    if JOIN in rb_actions:
        rhs_table_id, lhs_join_var, rhs_key_index = parse_join_expression(rb_actions[JOIN]['text'])
        join_record_iterator = join_tables_registry.get_iterator_by_table_id(rhs_table_id)
        if join_record_iterator is None:
            raise RBParsingError('Unable to find join table: "{}"'.format(rhs_table_id))
        join_map = HashJoinMap(join_record_iterator, rhs_key_index)

    if WHERE in rb_actions:
        where_expression = rb_actions[WHERE]['text']
        if re.search(r'[^!=]=[^=]', where_expression) is not None:
            raise RBParsingError('Assignments "=" are not allowed in "WHERE" expressions. For equality test use "=="')
        py_meta_params['__RBQLMP__where_expression'] = combine_string_literals(where_expression, string_literals)
    else:
        py_meta_params['__RBQLMP__where_expression'] = 'True'

    if UPDATE in rb_actions:
        update_expression = translate_update_expression(rb_actions[UPDATE]['text'], ' ' * 8)
        py_meta_params['__RBQLMP__writer_type'] = 'simple'
        py_meta_params['__RBQLMP__select_expression'] = 'None'
        py_meta_params['__RBQLMP__update_statements'] = combine_string_literals(update_expression, string_literals)
        py_meta_params['__RBQLMP__is_select_query'] = 'False'
        py_meta_params['__RBQLMP__top_count'] = 'None'

    py_meta_params['__RBQLMP__init_column_vars_select'] = generate_init_statements(column_vars, ' ' * 8)
    py_meta_params['__RBQLMP__init_column_vars_update'] = generate_init_statements(column_vars, ' ' * 4)

    if SELECT in rb_actions:
        top_count = find_top(rb_actions)
        py_meta_params['__RBQLMP__top_count'] = str(top_count) if top_count is not None else 'None'
        if 'distinct_count' in rb_actions[SELECT]:
            py_meta_params['__RBQLMP__writer_type'] = 'uniq_count'
        elif 'distinct' in rb_actions[SELECT]:
            py_meta_params['__RBQLMP__writer_type'] = 'uniq'
        else:
            py_meta_params['__RBQLMP__writer_type'] = 'simple'
        if EXCEPT in rb_actions:
            py_meta_params['__RBQLMP__select_expression'] = translate_except_expression(rb_actions[EXCEPT]['text'])
        else:
            select_expression = translate_select_expression_py(rb_actions[SELECT]['text'])
            py_meta_params['__RBQLMP__select_expression'] = combine_string_literals(select_expression, string_literals)
        py_meta_params['__RBQLMP__update_statements'] = 'pass'
        py_meta_params['__RBQLMP__is_select_query'] = 'True'

    if ORDER_BY in rb_actions:
        order_expression = rb_actions[ORDER_BY]['text']
        py_meta_params['__RBQLMP__sort_key_expression'] = combine_string_literals(order_expression, string_literals)
        py_meta_params['__RBQLMP__reverse_flag'] = 'True' if rb_actions[ORDER_BY]['reverse'] else 'False'
        py_meta_params['__RBQLMP__sort_flag'] = 'True'
    else:
        py_meta_params['__RBQLMP__sort_key_expression'] = 'None'
        py_meta_params['__RBQLMP__reverse_flag'] = 'False'
        py_meta_params['__RBQLMP__sort_flag'] = 'False'

    python_code = rbql_meta_format(py_script_body, py_meta_params)
    return (python_code, join_map)



def generic_run(query, input_iterator, output_writer, join_tables_registry=None, user_init_code=''):
    # New generic interface
    # join_tables_registry can just throw an exception if rhs table is not "B". The registry therefore can consist of a single table. Or even of No tables at all (e.g. for WEB version)
    pass #FIXME impl

    py_dst = None # FIXME
    if not py_dst.endswith('.py'):
        raise RBParsingError('python module file must have ".py" extension')

    python_code, join_map = parse_to_py(query, join_tables_registry, user_init_code) #FIXME
    execution_warnings = rb_transform(input_iterator, join_map, output_writer) #FIXME
    input_warnings = input_iterator.get_warnings()
    join_warnings = join_map.get_warnings()
    output_warnings = output_writer.get_warnings()
    warnings = input_warnings + join_warnings + execution_warnings + output_warnings


def csv_run(query, input_stream, input_delim, input_policy, output_stream, output_delim, output_policy, csv_encoding, custom_init_path=None):
    if input_delim == '"' and input_policy == 'quoted':
        raise csv_utils.CSVHandlingError('Double quote delimiter is incompatible with "quoted" policy')
    if input_delim != ' ' and input_policy == 'whitespace':
        raise csv_utils.CSVHandlingError('Only whitespace " " delim is supported with "whitespace" policy')

    if not is_ascii(query) and csv_encoding == 'latin-1':
        raise RBParsingError('To use non-ascii characters in query enable UTF-8 encoding instead of latin-1/binary')

    user_init_code = ''
    if custom_init_path is not None:
        user_init_code = make_user_init_code(custom_init_path)
    elif os.path.exists(default_init_source_path):
        user_init_code = make_user_init_code(default_init_source_path)

    join_tables_registry = csv_utils.FileSystemCSVRegistry(input_delim, input_policy, csv_encoding)
    input_iterator = csv_utils.CSVRecordIterator(input_stream, csv_encoding, input_delim, input_policy)
    output_writer = csv_utils.CSVWriter(output_stream, output_delim, output_policy)
    generic_run(query, input_iterator, output_writer, join_tables_registry, user_init_code)
    # FIXME return warnings, errors, etc



#def parse_to_py(query, py_dst, input_delim, input_policy, out_delim, out_policy, csv_encoding, custom_init_path=None):
#    FIXME remove this after implementing script writing
#    with codecs.open(py_dst, 'w', encoding='utf-8') as dst:
#        dst.write(rbql_meta_format(py_script_body, py_meta_params))


def make_warnings_human_readable(warnings):
    result = list()
    # FIXME we don't need this function in it's current form
    for warning_type, warning_value in warnings.items():
        elif warning_type == 'delim_in_simple_output':
            result.append('Some result set fields contain output separator.')
        elif warning_type == 'utf8_bom_removed':
            result.append('UTF-8 Byte Order Mark BOM was found and removed.')
        elif warning_type == 'defective_csv_line_in_input':
            result.append('Defective double quote escaping in input table. E.g. at line {}.'.format(warning_value))
        elif warning_type == 'defective_csv_line_in_join':
            result.append('Defective double quote escaping in join table. E.g. at line {}.'.format(warning_value))
        elif warning_type == 'input_fields_info':
            result.append(make_inconsistent_num_fields_hr_warning('input', warning_value))
        elif warning_type == 'join_fields_info':
            result.append(make_inconsistent_num_fields_hr_warning('join', warning_value))
        else:
            raise RuntimeError('Error: unknown warning type: {}'.format(warning_type))
    for w in result:
        assert w.find('\n') == -1
    return result


class RbqlPyEnv:
    def __init__(self):
        self.env_dir_name = None
        self.env_dir = None
        self.module_path = None
        self.module_name = None

    def __enter__(self):
        tmp_dir = tempfile.gettempdir()
        self.env_dir_name = 'rbql_{}_{}'.format(time.time(), random.randint(1, 100000000)).replace('.', '_')
        self.env_dir = os.path.join(tmp_dir, self.env_dir_name)
        self.module_name = 'worker_{}'.format(self.env_dir_name)
        module_filename = '{}.py'.format(self.module_name)
        self.module_path = os.path.join(self.env_dir, module_filename)
        os.mkdir(self.env_dir)
        shutil.copy(os.path.join(rbql_home_dir, 'csv_utils.py'), self.env_dir)
        return self

    def import_worker(self):
        # We need to add env_dir to sys.path after worker module has been generated to avoid calling `importlib.invalidate_caches()`
        # Description of the problem: http://ballingt.com/import-invalidate-caches/
        assert os.path.exists(self.module_path), 'Unable to find generated module at {}'.format(sys.module_path)
        sys.path.append(self.env_dir)
        return importlib.import_module(self.module_name)

    def remove_env_dir(self):
        # Should be called on success only: do not put in __exit__. In case of error we may need to have the generated module
        try:
            shutil.rmtree(self.env_dir)
        except Exception:
            pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            sys.path.remove(self.env_dir)
        except ValueError:
            pass

