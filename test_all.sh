#!/usr/bin/env bash

dir_name=$( basename "$PWD" )

export PYTHONPATH="./rbql-py:$PYTHONPATH" 

if [ "$dir_name" != "RBQL" ] && [ "$dir_name" != "rbql_core" ]; then
    echo "Error: This test must be run from RBQL dir. Exiting"
    exit 1
fi


die_if_error() {
    if [ $1 != 0 ]; then
        echo "One of the tests failed. Exiting"
        exit 1
    fi
}


cleanup_tmp_files() {
    rm tmp_out.csv 2> /dev/null
    rm tmp_err 2> /dev/null
    rm random_tmp_table.txt 2> /dev/null
    rm speed_test.csv 2> /dev/null
    rm rbql_warning.out 2> /dev/null
    rm test/js_column_infos.txt 2> /dev/null
    rm test/python_column_infos.txt 2> /dev/null
}


run_unit_tests="yes"
run_pandas_tests="yes"
run_python_tests="yes"
run_node_tests="yes"
cleanup_mode="no"


py3_version=$( python3 --version 2> /dev/null )
rc=$?
if [ "$rc" != 0 ] || [ -z "$py3_version" ]; then
    echo "ERROR! python3 was not found. Exiting"  1>&2
    exit 1
fi


while [[ $# -gt 0 ]]; do
    key="$1"
    case "$key" in
        --skip_unit_tests)
        run_unit_tests="no"
        ;;
        --skip_pandas_tests)
        run_pandas_tests="no"
        ;;
        --skip_node_tests)
        run_node_tests="no"
        ;;
        --skip_python_tests)
        run_python_tests="no"
        ;;
        --cleanup)
        cleanup_mode="yes"
        ;;
        *)
        echo "Unknown option '$key'"
        exit 1
        ;;
    esac
    shift
done


cleanup_tmp_files

if [ "$cleanup_mode" == "yes" ]; then
    exit 0
fi

py_rbql_version=$( python3 -m rbql --version )


if [ $run_node_tests == "yes" ]; then
    node_version=$( node --version 2> /dev/null )
    rc=$?
    if [ "$rc" != 0 ] || [ -z "$node_version" ]; then
        echo "WARNING! Node.js was not found. Skipping node unit tests"  1>&2
        run_node_tests="no"
    fi
fi


python3 test/test_csv_utils.py --create_big_csv_table speed_test.csv


if [ $run_unit_tests == "yes" ]; then
    if [ "$run_python_tests" == "yes" ]; then
        python3 -m unittest test.test_csv_utils
        die_if_error $?

        python3 -m unittest test.test_rbql
        die_if_error $?

        python3 -m unittest test.test_rbql_sqlite
        die_if_error $?

        if [ "$run_pandas_tests" == "yes" ]; then
            python3 -m unittest test.test_rbql_pandas
            die_if_error $?
        fi

        python3 -m unittest test.test_mad_max
        die_if_error $?
    fi

    python3 test/test_csv_utils.py --create_random_csv_table random_tmp_table.txt

    if [ "$run_node_tests" == "yes" ]; then
        js_rbql_version=$( node rbql-js/cli_rbql.js --version )
        if [ "$py_rbql_version" != "$js_rbql_version" ]; then
            echo "Error: version missmatch between rbql.py ($py_rbql_version) and rbql.js ($js_rbql_version)"  1>&2
            exit 1
        fi
        cd test

        node test_csv_utils.js --run-random-csv-mode ../random_tmp_table.txt
        die_if_error $?

        node test_rbql.js
        die_if_error $?

        node test_csv_utils.js
        die_if_error $?

        cd ..
    fi
fi

if [ $run_unit_tests == "yes" ] && [ "$run_python_tests" == "yes" ] && [ "$run_node_tests" == "yes" ]; then
    if ! cmp -s "test/js_column_infos.txt" "test/python_column_infos.txt"; then
        echo "Test Failed: column name parsing differs between python and js version." 1>&2
        echo "Compare: diff test/js_column_infos.txt test/python_column_infos.txt" 1>&2
    fi
fi


# Testing unicode separators
md5sum_expected="bdb725416a7b17e64034e0a128c6bb96"
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --query 'select a2, a1' --delim $(echo -e "\u2063") --policy simple --input test/csv_files/invisible_separator_u2063.txt --encoding utf-8 | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "python3 unicode separator test FAIL!"  1>&2
        exit 1
    fi
fi
if [ "$run_node_tests" == "yes" ]; then
    md5sum_test=($( node ./rbql-js/cli_rbql.js --query 'select a2, a1' --delim $(echo -e "\u2063") --policy simple --input test/csv_files/invisible_separator_u2063.txt --encoding utf-8 | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "node unicode separator test FAIL!"  1>&2
        exit 1
    fi
fi


# Testing unicode queries
md5sum_expected="e1fe4bd13b25b2696e3df2623cd0f134"
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --query "select a2, '$(echo -e "\u041f\u0440\u0438\u0432\u0435\u0442")' + ' ' + a1" --delim TAB --policy simple --input test/csv_files/movies.tsv --encoding utf-8 | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "python3 unicode query test FAIL!"  1>&2
        exit 1
    fi
fi
if [ "$run_node_tests" == "yes" ]; then
    md5sum_test=($(node ./rbql-js/cli_rbql.js --query "select a2, '$(echo -e "\u041f\u0440\u0438\u0432\u0435\u0442")' + ' ' + a1" --delim TAB --policy simple --input test/csv_files/movies.tsv --encoding utf-8 | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "node unicode query test FAIL!"  1>&2
        exit 1
    fi
fi


# Testing broken pipe
md5sum_expected="c5693303e0cc70fcd068df626f49bf75"
if [ "$run_python_tests" == "yes" ]; then
    rm rbql_warning.out 2> /dev/null
    md5sum_test=($(python3 -m rbql --input test/csv_files/movies.tsv --query 'select a2, None, a1' --delim TAB 2> rbql_warning.out | head -n 10 | md5sum))
    warning_test=$( cat rbql_warning.out )
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "Python3 broken pipe test fail!"  1>&2
        exit 1
    fi
    if [ "$warning_test" != "Warning: None values in output were replaced by empty strings" ]; then
        echo "Python3 broken pipe test fail: wrong warning!"  1>&2
        exit 1
    fi

    rm rbql_warning.out 2> /dev/null
fi


# Testing colored output
md5sum_expected="4798e34af6a68d76119048ed2cf0a0c2"
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --input test/csv_files/movies.tsv --query 'select a2, None, a1' --delim TAB --color 2> /dev/null | head -n 10 | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "Python colored output test fail!"  1>&2
        exit 1
    fi
fi
md5sum_expected="27a29bfe96e6dceacdc9b6ed197a9158"
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --input test/csv_files/universities.monocolumn --query 'select str(NR) + " " + a1 where a1.find(" of ") != -1' --policy monocolumn --color | head -n 20 | md5sum))
    # Monocolumn policy should disregard --color parameter
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "Python monocolumn non-colored output test fail: monocolumn policy should disregard --column argument!"  1>&2
        exit 1
    fi
fi
md5sum_expected="b259b60f8ac1f51a1a1b9d6db416c5f9"
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --input test/csv_files/rfc_newlines_in_header.csv --delim , --policy quoted_rfc --query 'select NR, a3 + a1, a2, NF' --color | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "Python colored output rfc test fail!"  1>&2
        exit 1
    fi
fi


# Testing warnings
if [ "$run_python_tests" == "yes" ]; then
    expected_warning="Warning: Number of fields in \"input\" table is not consistent: e.g. record 1 -> 8 fields, record 3 -> 6 fields"
    actual_warning=$( python3 -m rbql --input test/csv_files/movies_variable_width.tsv --delim TAB --policy simple --query 'select a1, a2' 2>&1 1> /dev/null )
    if [ "$expected_warning" != "$actual_warning" ]; then
        echo "expected_warning= '$expected_warning' != '$actual_warning' = actual_warning"  1>&2
        exit 1
    fi
fi

if [ "$run_node_tests" == "yes" ]; then
    expected_warning="Warning: Number of fields in \"input\" table is not consistent: e.g. record 1 -> 8 fields, record 3 -> 6 fields"
    actual_warning=$( node rbql-js/cli_rbql.js --input test/csv_files/movies_variable_width.tsv --delim TAB --policy simple --query 'select a1, a2' 2>&1 1> /dev/null )
    if [ "$expected_warning" != "$actual_warning" ]; then
        echo "expected_warning= '$expected_warning' != '$actual_warning' = actual_warning"  1>&2
        exit 1
    fi
fi



# Testing errors
if [ "$run_python_tests" == "yes" ]; then
    expected_error="Error [query execution]: At record 1, Details: name 'unknown_func' is not defined"
    actual_error=$( python3 -m rbql --input test/csv_files/countries.csv --query 'select top 10 unknown_func(a1)' --delim , --policy quoted 2>&1 )
    if [ "$expected_error" != "$actual_error" ]; then
        echo "expected_error = '$expected_error' != '$actual_error' = actual_error"  1>&2
        exit 1
    fi
fi

if [ "$run_node_tests" == "yes" ]; then
    expected_error="Error [query execution]: At record 1, Details: unknown_func is not defined"
    actual_error=$( node rbql-js/cli_rbql.js --input test/csv_files/countries.csv --query 'select top 10 unknown_func(a1)' --delim , --policy quoted 2>&1 )
    if [ "$expected_error" != "$actual_error" ]; then
        echo "expected_error = '$expected_error' != '$actual_error' = actual_error"  1>&2
        exit 1
    fi
fi


# Testing with-headers / named columns in CLI
md5sum_expected=($( md5sum test/csv_files/expected_result_14.csv ))
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --input test/csv_files/countries.csv --query "select top 5 a.country, a['GDP per capita'] order by int(a['GDP per capita']) desc" --delim , --with-headers | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "CLI Python with-headers test FAIL!"  1>&2
        exit 1
    fi
fi


if [ "$run_node_tests" == "yes" ]; then
    # Using `NaN || 1000 * 1000` trick below to return 1M on NaN and make sure that we skip the header. Otherwise the header line would be the max
    md5sum_test=($( node ./rbql-js/cli_rbql.js --input test/csv_files/countries.csv --query "select top 5 a.country, a['GDP per capita'] order by parseInt(a['GDP per capita']) || 1000 * 1000 desc" --delim , --with-headers | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "CLI JS with-headers test FAIL!"  1>&2
        exit 1
    fi
fi



# Testing CLI errors and warnings
output=$( python3 -m rbql --delim , --query "SELECT top 3 a1, foobarium(a2)" --input test/csv_files/countries.csv 2>&1 )
rc=$?
if [ $rc != 1 ] || [[ $output != *"name 'foobarium' is not defined"* ]]; then
    echo "rbql-py does not produce expected error. rc:$rc, output:$output "  1>&2
    exit 1
fi

output=$( python3 -m rbql --delim , --query "SELECT top 3 a1, None, a2" --input test/csv_files/countries.csv 2>&1 > /dev/null )
rc=$?
if [ $rc != 0 ] || [[ $output != *"Warning: None values in output were replaced by empty strings"* ]]; then
    echo "rbql-py does not produce expected warning. rc:$rc, output:$output "  1>&2
    exit 1
fi


output=$( node ./rbql-js/cli_rbql.js --delim , --query "SELECT top 3 a1, foobarium(a2)" --input test/csv_files/countries.csv 2>&1 )
rc=$?
if [ $rc != 1 ] || [[ $output != *"foobarium is not defined"* ]]; then
    echo "rbql-js does not produce expected error. rc:$rc, output:$output "  1>&2
    exit 1
fi

output=$( node ./rbql-js/cli_rbql.js --delim , --query "SELECT top 3 a1, null, a2" --input test/csv_files/countries.csv 2>&1 > /dev/null )
rc=$?
if [ $rc != 0 ] || [[ $output != *"Warning: null values in output were replaced by empty strings"* ]]; then
    echo "rbql-js does not produce expected warning. rc:$rc, output:$output "  1>&2
    exit 1
fi



rand_val=$[ $RANDOM % 2 ]
if [ $rand_val = 1 ]; then
    # TODO randomly add --trim_spaces option for JS too
    strip_spaces_option=" --strip-spaces"
    trim_spaces_option=" --trim-spaces"
else
    strip_spaces_option=""
    trim_spaces_option=""
fi
echo "strip spaces option: '$strip_spaces_option'"


# Testing performance
if [ "$run_python_tests" == "yes" ]; then
    start_tm=$(date +%s.%N)
    python3 test/test_csv_utils.py --dummy_csv_speedtest speed_test.csv > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "Python reference split test took $elapsed seconds"

    start_tm=$(date +%s.%N)
    python3 -m rbql --input speed_test.csv --delim , --policy quoted --query 'select a2, a1, a2, NR where int(a1) % 2 == 3' > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "Python empty result select query took $elapsed seconds. Reference value: 2.6 seconds"

    start_tm=$(date +%s.%N)
    python3 -m rbql --input speed_test.csv --delim , --policy quoted --query 'select a2, a1, a2, NR where int(a1) % 2 == 0' $strip_spaces_option > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "Python simple select query took $elapsed seconds. Reference value: 3 seconds"

    start_tm=$(date +%s.%N)
    python3 -m rbql --input speed_test.csv --delim , --policy quoted --query 'select max(a1), count(*), a2 where int(a1) > 15 group by a2' > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "Python GROUP BY query took $elapsed seconds. Reference value: 2.6 seconds"
fi

if [ "$run_node_tests" == "yes" ]; then
    start_tm=$(date +%s.%N)
    node ./rbql-js/cli_rbql.js --input speed_test.csv --delim , --policy quoted --query 'select a2, a1, a2, NR where parseInt(a1) % 2 == 3' $trim_spaces_option > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "JS empty result select query took $elapsed seconds. Reference value: 1.1 seconds"

    start_tm=$(date +%s.%N)
    node ./rbql-js/cli_rbql.js --input speed_test.csv --delim , --policy quoted --query 'select a2, a1, a2, NR where parseInt(a1) % 2 == 0' > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "JS simple select query took $elapsed seconds. Reference value: 2.3 seconds"

    start_tm=$(date +%s.%N)
    node ./rbql-js/cli_rbql.js --input speed_test.csv --delim , --policy quoted --query 'select max(a1), count(*), a2 where parseInt(a1) > 15 group by a2' $trim_spaces_option > /dev/null
    end_tm=$(date +%s.%N)
    elapsed=$( echo "$start_tm,$end_tm" | python3 -m rbql --delim , --query 'select float(a2) - float(a1)' )
    echo "JS GROUP BY query took $elapsed seconds. Reference value: 1.1 seconds"
fi



# Testing generic CLI
md5sum_expected=($( md5sum test/csv_files/expected_result_4.tsv ))
if [ "$run_python_tests" == "yes" ]; then
    md5sum_test=($(python3 -m rbql --delim TAB --query "select a1,a2,a7,b2,b3,b4 left join test/csv_files/countries.tsv on a2 == b1 where 'Sci-Fi' in a7.split('|') and b2!='US' and int(a4) > 2010" $strip_spaces_option < test/csv_files/movies.tsv | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "CLI Python test FAIL!"  1>&2
        exit 1
    fi

    # XXX theorethically this test can randomly fail because sleep timeout is not long enough
    (echo "select select a1" && sleep 0.5 && echo "select a1, nonexistent_func(a2)" && sleep 0.5 && echo "select a1,a2,a7,b2,b3,b4 left join test/csv_files/countries.tsv on a2 == b1 where 'Sci-Fi' in a7.split('|') and b2!='US' and int(a4) > 2010") | python3 -m rbql --delim '\t' --input test/csv_files/movies.tsv --output tmp_out.csv $strip_spaces_option > /dev/null
    md5sum_test=($(cat tmp_out.csv | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "Interactive CLI Python test FAIL!"  1>&2
        exit 1
    fi
fi


if [ "$run_node_tests" == "yes" ]; then
    md5sum_test=($( node ./rbql-js/cli_rbql.js --delim TAB --query "select a1,a2,a7,b2,b3,b4 left join test/csv_files/countries.tsv on a2 == b1 where a7.split('|').includes('Sci-Fi') && b2!='US' && a4 > 2010" $trim_spaces_option < test/csv_files/movies.tsv | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "CLI JS test FAIL!"  1>&2
        exit 1
    fi

    # XXX theorethically this test can randomly fail because sleep timeout is not long enough
    (echo "select select a1" && sleep 0.5 && echo "select a1, nonexistent_func(a2)" && sleep 0.5 && echo "select a1,a2,a7,b2,b3,b4 left join test/csv_files/countries.tsv on a2 == b1 where a7.split('|').includes('Sci-Fi') && b2!='US' && a4 > 2010") | node ./rbql-js/cli_rbql.js --input test/csv_files/movies.tsv --output tmp_out.csv --delim '\t' $trim_spaces_option > /dev/null
    md5sum_test=($(cat tmp_out.csv | md5sum))
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "Interactive CLI JS test FAIL!"  1>&2
        exit 1
    fi
fi


# Testing sqlite CLI
if [ "$run_python_tests" == "yes" ]; then
    md5sum_expected=($( md5sum test/sqlite_files/expected_result_1.csv ))
    expected_warning="Warning: None values in output were replaced by empty strings"
    python3 -m rbql sqlite test/sqlite_files/mental_health_single_table.sqlite --input Question --query 'select top 100 *, a2 * 10, len(a.questiontext) if a.questiontext else 0 WHERE a1 is None or a1.find("your") != -1' > tmp_out.csv 2> tmp_err.txt
    md5sum_test=($( md5sum tmp_out.csv ))
    test_warning=$( cat tmp_err.txt )
    if [ "$md5sum_expected" != "$md5sum_test" ]; then
        echo "rbql sqlite cli test fail!"  1>&2
        exit 1
    fi
    if [ "$expected_warning" != "$test_warning" ]; then
        echo "rbql sqlite cli test fail: wrong warning!"  1>&2
        exit 1
    fi
fi




cleanup_tmp_files

echo "Finished tests"
