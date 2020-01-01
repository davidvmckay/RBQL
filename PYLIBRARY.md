# Using RBQL as python library

Disclaimer: RBQL is not an SQL server and it is not suitable for multiple automatic queries.  
All RBQL queries are supposed to be manually entered by human users of your application.  


#### Installation:
You can either use pip or just clone the rbql-py repository:  
```
$ pip install rbql
```
OR  
```
$ git clone https://github.com/mechatroner/rbql-py.git 
```

## API

rbql library provides 3 main functions that you can use:  

1. [rbql.query_table(...)](#rbqlquery_table)  
2. [rbql_csv.query_csv(...)](#rbqlquery_csv)  
3. [rbql.query(...)](#rbqlquery)  


### rbql.query_table(...)

Run user query against a list of records and put the result set in the output list.  

#### Signature:  
  
`rbql.query_table(user_query, input_table, output_table, output_warnings, join_table=None)`


#### Parameters: 
* _user_query_: **string**  
  query that user of your app manually enters in some kind of input field.  
* _input_table_: **list**  
  list with input records  
* _output_table_: **list**  
  output records will be stored here after the query completion
* _output_warnings_: **list**  
  warnings will be stored here after the query completion. If no warnings - the list would be empty
* _join_table_: **list**  
  list with join table so that user can use join table B in input queries  


#### Usage example:
```
import rbql
input_table = [
    ['Roosevelt',1858,'USA'],
    ['Napoleon',1769,'France'],
    ['Dmitri Mendeleev',1834,'Russia'],
    ['Jane Austen',1775,'England'],
    ['Hayao Miyazaki',1941,'Japan'],
]
user_query = 'SELECT a1, a2 % 1000 WHERE a3 != "USA" LIMIT 3'
output_table = []
warnings = []
rbql.query_table(user_query, input_table, output_table, warnings)
for record in output_table:
    print(','.join([str(v) for v in record]))
```



### rbql.query_csv(...)

Run user query against input_path CSV file and save it as output_path CSV file.  

#### Signature:  
  
`rbql.query_csv(user_query, input_path, input_delim, input_policy, output_path, output_delim, output_policy, csv_encoding, output_warnings)`  
  
#### Parameters:
* _user_query_: **string**  
  query that user of your application manually enters in some kind of input field.  
* _input_path_: **string**  
  path of the input csv table  
* _input_delim_: **string**  
  field separator character in input table  
* _input_policy_: **string**  
  allowed values: `'simple'`, `'quoted'`  
  along with input_delim defines CSV dialect of input table. "quoted" means that separator can be escaped inside double quoted fields  
* _output_path_: **string**  
  path of the output csv table  
* _output_delim_: **string**  
  same as input_delim but for output table  
* _output_policy_: **string**  
  same as input_policy but for output table  
* _csv_encoding_: **string**  
  allowed values: `'latin-1'`, `'utf-8'`  
  encoding of input, output and join tables (join table can be defined inside the user query)  
* _output_warnings_: **list**  
  warnings will be stored here after the query completion. If no warnings - the list would be empty


#### Usage example

```
import rbql
from rbql import rbql_csv
user_query = 'SELECT a1, int(a2) % 1000 WHERE a3 != "USA" LIMIT 5'
warnings = []
rbql_csv.query_csv(user_query, 'input.csv', ',', 'quoted', 'output.csv', ',', 'quoted', 'utf-8', warnings)
print(open('output.csv').read())
```


### rbql.query(...)

Allows to run queries against any kind of structured data.  
You will have to implement special wrapper classes for your custom data structures and pass them to the `rbql.query(...)` function.  

#### Signature:
  
`query(user_query, input_iterator, output_writer, output_warnings, join_tables_registry=None)`  
  
#### Parameters:
* _user_query_: **string**  
  query that user of your app manually enters in some kind of input field.  
* _input_iterator_:  **RBQLInputIterator**  
  special object which iterates over input records. E.g. over remote table  
* _output_writer_:  **RBQLOutputWriter**  
  special object which stores output records somewhere. E.g. to a python list  
* _output_warnings_: **list**  
  warnings will be stored here after the query completion. If no warnings - the list would be empty
* _join_tables_registry_: **RBQLJoinTablesRegistry**  
  special object which provides **RBQLInputIterator** iterators for join tables (e.g. table "B") which user can refer to in queries.  


#### Usage example
See `rbql.query(...)` usage in RBQL [tests](https://github.com/mechatroner/RBQL/blob/master/test/test_rbql.py)  
Examples of implementation of **RBQLInputIterator**, **RBQLOutputWriter** and **RBQLJoinTablesRegistry** classes can also be found in the RBQL repository  