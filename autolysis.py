# /// script
# requires-python = ">3.12"
# dependencies = [
#     'requests<3' ,
#     'python-dotenv',
#     'pandas',
#     'numpy',
#     'seaborn',
#     'matplotlib',
#     'scipy',
#     'chardet',
# ]
# ///


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv
import json
import requests
import io
import traceback
import base64
import sys
import os
import chardet
import time
import concurrent.futures

start = time.time()
print("started: ")

AIPROXY_TOKEN = os.environ.get("AIPROXY_TOKEN")
# load_dotenv()

# AIPROXY_TOKEN = os.getenv('AIPROXY_TOKEN')

URL = "http://aiproxy.sanand.workers.dev/openai/v1/chat/completions"

MODEL = "gpt-4o-mini"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AIPROXY_TOKEN}"
}










#DESIGNING FUNCTIONS FOR API REQUESTS TO OPENAI
def request_llm(functions,user_content,sys_content,func_name,code_list=[],error_list=[],limit=3):
    if limit != 3:
        user_content = code_list[-1] + "\n" + error_list[-1]
    DATA = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_content}
            ],
            "functions":json.loads(json.dumps(functions)),
            "function_call":{"name":func_name},
            }
    response = requests.post(URL, headers=HEADERS, json=DATA,timeout=120)
    return response

def execute_llm(functions,user_content,sys_content,func_name):
    limit = 3
    code_list = []
    error_list = []
    return_args = None
    while limit > 0:
        try:
            res = request_llm(functions,user_content,sys_content,func_name,code_list,error_list,limit)
            # print(res.json())
            return_args = json.loads(res.json()['choices'][0]['message']['function_call']['arguments'])
            code = return_args["python_code"]
            code_list.append(code)
            exec(code)
            return True , code_list , limit ,return_args
        except Exception as e:
            buffer = io.StringIO()
            traceback.print_exc(file=buffer)
            buffer_output = buffer.getvalue()
            error = '\n'.join(buffer_output.split('\n')[3:])
            error_list.append(error)
            print("Error !! Trying again.")
            print(error)
            buffer.close()
        finally:
            limit -= 1
    return False , error_list , limit ,return_args












# LOADING DATASET
data = ""
with open(file=sys.argv[1], mode="rb") as f:
    result = chardet.detect(f.read())
with open(file=sys.argv[1], mode="r",encoding=result['encoding']) as f:
    data = ''.join([f.readline() for i in range(10)])
df = pd.read_csv(sys.argv[1],encoding=result['encoding'])
os.makedirs(sys.argv[1].split(".csv")[0].split("\")[-1],exist_ok=True)












#COLUMN_METADATA
content = """Analyse the given dataset.The first line is the header, and the subsequent lines are sample data.
    Columns may have unclean data in them.Ignore those cells. Infer the data type by considering majority of the values in each column.
    Also consider name of the column while deciding its data type.
    Supported types are 'str' , 'int', 'datetime','boolean','float'
"""

functions =[
   {
      "name":"get_column_type",
      "description":"Identify column names and their data types from a csv file for use in python for further processing",
      "parameters":{
        "type":"object",
        "properties":{
            "column_metadata":{
              "type":"array",
              "description":"Array of data types of each column.",
              "items":{
                  "type":"object",
                  "properties":{
                    "column_name":{
                        "type":"string",
                        "description":"Name of the column."
                    },
                    "column_type":{
                        "type":"string",
                        "description":"The data type of the column (eg. integer, string)"
                    }
                  },
                  "required":[
                    "column_name",
                    "column_type"
                  ]
              },
              "minItems":1
            }
        },
        "required":[
            "column_metadata"
        ]
      }
    }
]


r = request_llm(functions,f"{data}",content,'get_column_type')

res_column_dtypes = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['column_metadata']
print(res_column_dtypes)












#SOME PREPROCESSING
count = 0
for column in res_column_dtypes:
  col_name = column['column_name']
  col_type = column['column_type']
  if (col_type == 'int' or col_type == 'float') and df[col_name].dtype == 'object' or df[col_name].dtype == 'string':
    df[col_name] = pd.to_numeric(df[col_name],errors='coerce')
    count+=1
  elif col_type == 'datetime' and df[col_name].dtype == 'object':
    df[col_name] = pd.to_datetime(df[col_name],errors='coerce')
    count+=1
  elif col_type == 'boolean' and df[col_name].dtype == 'object':
    df[col_name] = df[col_name].astype('bool')
    count+=1
  elif col_type == 'str' and ('float' in str(df[col_name].dtype) or 'int' in str(df[col_name].dtype)):
    if 'float' in str(df[col_name].dtype):
      column['column_type'] = 'float'
    if 'int' in str(df[col_name].dtype):
      column['column_type'] = 'int'
    count+=1


print(count)
print(df.info())















#IMPUTING NULL VALUES
print(df.isnull().sum())
null_details = json.loads(df.isnull().sum().to_json())
null_details

null_columns = dict()

for column in null_details.keys():
  if null_details[column] > 0:
    null_columns[column] = json.loads(df[column].describe().to_json())

print(null_columns)

content = (
    "The data provided consists of only those column names  which contain null/nan values and the corresponding statistics of those columns."
    "Figure out from the statistics with what to replace the null/nan values. Is it with either `mean` or `median` or `most frequent` or some `constant value` ."
    "In case you cannot decide what to fill null values with,fill them with `Unknown`."
    "Generate python code to replace null/nan in the columns provide with either `mean` or `median` or `most frequent` or some `constant value` ."
    "Do not add comments to the code."
    "Do not make your own data, dataset is stored in the dataframe named ```df``` ."
)



functions = [
    {
        "name": "replace_null_values",
        "description":"Generate python code without comments to replace null values in columns with either `mean` or `median` or 'most frequent' or `constant value`. Provide column names with what to replace the nan/null values with.Also send names of the modules that were used.",
        "parameters":{
            "type":"object",
            "properties":{
                "python_code":{
                    "type":"string",
                    "description":"Generate python code without comments to replace nan/null values."
                },
                "null_cols":{
                    "type":"array",
                    "description":"Array of column names and with what to replace nan/null values with.",
                    "items":{
                        "type":"object",
                        "properties":{
                          "column_name":{
                              "type":"string",
                              "description":"Name of the column."
                          },
                          "replace_with":{
                              "type":"string",
                              "description":"A string denoting with what to replace the null values .Either `mean` or `median` or `most frequent` or `constant value`"
                          },
                          "reason":{
                              "type":"string",
                              "description":"Give reason as to why did you replace null/nan values with either `mean` or `median` or `most frequent` or `constant value`"
                          }
                        },
                        "required":[
                          "column_name",
                          "replace_with",
                          "reason"
                        ]
                    },
                },
                "dependencies":{
                    "type":"string",
                    "description":"Give comma seperated names of the modules that were used in this script."
                }
            },
            "required":[
                "python_code",
                "null_cols",
                "dependencies"
            ]
        }
    }
]

flag , code_list , limit ,return_args = execute_llm(functions,f"{null_columns}",content,'replace_null_values')
print(return_args)
print(return_args['python_code'])

res_null_cols_reason = return_args['null_cols']

print(df.isnull().sum())




















#BINNABLE GRAPH
numeric_columns = []
for column in res_column_dtypes:
  col_name = column['column_name']
  col_type = column['column_type']
  if col_type == 'int' or col_type == 'float':
    numeric_columns.append({col_name:json.loads(df.describe()[col_name].to_json())})

content = (
    "The data provided consists of column names which are numeric and the statistics related to those columns."
    "From these statistics decide which columns are binnable and which are not."
    "Seperate those columns which are binnable and which are not binnable alsong with a reason."
    "Consider those columns which are binnable and generate a subplot of graphs for each of the column which is binnable."
    "Each graph in the subplot should be chosen such that it showcases the binnable property of a column."
    "Get the column names from the data provided."
    "Generate python code to create a subplot of graphs."
    "Make use of modules like matplotlib and seaborn if needed."
    "Do not add any comments to python code."
    "Do not make your own data,the dataset is stored in dataframe named ```df``` ."
    "Export/save the chart/subplot as png file."
    f"save the chart in {sys.argv[1].split(".csv")[0].split("\")[-1]} folder."
)

functions = [
    {
      "name": "generate_chart_binnable",
      "description":"Identify those columns which are binnable and also which are not binnable.Also give reason for being binnable or not.Generate pyton code without comments for creating subplot as specified in prompt.Export the subplot chart as png file and provide name of png file created.",
      "parameters":{
            "type":"object",
            "properties":{
                "python_code":{
                    "type":"string",
                    "description":"Generate python code without comments for creating subplot as mentioned in the prompt."
                },
                "chart_name":{
                    "type":"string",
                    "description":"Name of the png file created."
                },
                "binnable_cols":{
                    "type":"array",
                    "description":"Array of all  column names provided in the data denoting True or False. True if binnable else False otherwise.",
                    "items":{
                        "type":"object",
                        "properties":{
                          "column_name":{
                              "type":"string",
                              "description":"Name of the column."
                          },
                          "is_binnable":{
                              "type":"boolean",
                              "description":"A boolean value(True/False) representing if a particular column is binnable or not"
                          },
                          "reason":{
                              "type":"string",
                              "description":"Give reason as to why a particular column is binnable or not."
                          }
                        },
                        "required":[
                          "column_name",
                          "is_binnable",
                          "reason"
                        ]
                    },
                },
                "dependencies":{
                    "type":"string",
                    "description":"Give comma seperated names of the modules that were used in this script."
                }
            },
            "required":[
                "python_code",
                "chart_name",
                "binnable_cols",
                "dependencies"
            ]
        }
      }
]

print("Before : ",len(numeric_columns))

flag , code_list , limit ,return_args = execute_llm(functions,f"{numeric_columns}",content,'generate_chart_binnable')

print(return_args['python_code'])
print("After : ",len(return_args['binnable_cols']))

res_binnable_cols_reason = return_args['binnable_cols']
CHART_BINNABLE = return_args['chart_name']


# CORRELATION MATRIX AND SCATTERPLOT OF HIGHEST CORRELATION COLUMNS
content = (
"You are given a dataset with variable ```df``` ."
"Generate a correlation matrix for the dataset and identify the pair of columns with the highest correlation (excluding 1.0 correlations)."
"Then, generate a scatter plot for this pair of columns using matplotlib."
"The plot should have appropriate labels and title."
f"Save/Exort both the scatter plot and heatmap of the correlation matrix separately in two png files inside {sys.argv[1].split(".csv")[0].split("\")[-1]} folder."
)

user_content = """
Generate a correlation matrix for the dataset and identify the pair of columns with the highest correlation(excluding 1.0 correlations).
Then, generate a scatter plot for this pair of columns.
The dataset is already loaded inside variable ```df``` so dont read the dataset again.
And the dataset contains even categorical values so omit those values using `numeric_only` parameter.
You can use matplotlib and seaborn also if necessary.
Do not add any comments to python code.
"""

functions = [
   {
        "name": "get_correlation_plot",
        "description": "Generate Python code without comments to compute a correlation matrix of the dataset, find the highest correlated columns (excluding 1.0), and create a scatterplot of those columns.Save/Export both, the scatter plot and heatmap of the correlation matrix separately in two png files and provide name of png files created.",
        "parameters": {
            "type": "object",
            "properties": {
                "python_code": {
                    "type": "string",
                    "description": "Python code to generate the correlation matrix and scatterplot of the highest correlation columns."
                },
                "heatmap_chart_name":{
                   "type": "string",
                   "description":"Name of the png file created for heatmap."
                },
                "scatter_chart_name":{
                   "type": "string",
                   "description":"Name of the png file created for scatterplot."
                }
            },
            "required": ["python_code","heatmap_chart_name","scatter_chart_name"]
        }
    }
]


flag,code_list,limit,return_args = execute_llm(functions,user_content,content,"get_correlation_plot")

print(return_args['python_code'])

CHART_HEATMAP = return_args['heatmap_chart_name']
CHART_SCATTER = return_args['scatter_chart_name']















#SKEWNESS FROM BINNABLE CHART
content = """Analyse the given chart properly which contains subplot of histograms of different columns with column names on x-axis.
Figure out the  column names which are left skewed, column names which are right skewed and column names which are nearly/almost normally distributed.
Three category names allowed are `Right Skewed` , `Left Skewed` and `Normally Distributed` .
"""

functions =[
   {
      "name":"skew_category",
      "description":"Identify column names based on skewness as provided in the prompt.",
      "parameters":{
        "type":"object",
        "properties":{
            "left_skewed":{
                "type":"array",
                "description":"Array of column names belonging to a left skewed category.",
                "items":{
                    "type":"string",
                    "description":"Name of the column."
                }
            },
            "right_skewed":{
                "type":"array",
                "description":"Array of column names belonging to a right skewed category.",
                "items":{
                    "type":"string",
                    "description":"Name of the column."
                }
            },
            "normally_distributed":{
                "type":"array",
                "description":"Array of column names belonging to a normally distributed category.",
                "items":{
                    "type":"string",
                    "description":"Name of the column."
                }
            }
        },
        "required":[
            "left_skewed",
            "right_skewed",
            "normally_distributed",
        ]
      }
   }
]

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
  
image_path = sys.argv[1].split(".csv")[0].split("\")[-1]+"/"+CHART_BINNABLE

# Getting the base64 string
base64_image = encode_image(image_path)

graph_content = [
          {
            "type": "text",
            "text": "Analyse this image.",
          },
          {
            "type": "image_url",
            "image_url": {
              "url":  f"data:image/png;base64,{base64_image}"
            },
          }
]

r = request_llm(functions,graph_content,content,'skew_category')
res_left_skewed = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['left_skewed']
res_right_skewed = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['right_skewed']
res_normally_distributed = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['normally_distributed']


print("LEFT SKEWED : ",res_left_skewed)
print("RIGHT SKEWED : ",res_right_skewed)
print("NORMALLY DISTRIBUTED : ",res_normally_distributed)














functions = [
    {
        "name": "analyze_chart",
        "parameters": {
            "type": "object",
            "properties": {
                "metadata": {"type": "string", "description": "Chart description or additional context"},
                "extracted_insights": {"type": "string", "description": "Extracted insights from the chart"}
            },
            "required": [
                "metadata", 
                "extracted_insights"
            ]
        }
    },
    {
        "name": "readME_md_creator",
        "parameters": {
            "type": "object",
            "properties" :{
                "readme_content": {"type":"string" ,"description":"Create a README.md which is well-structured, using headers, lists, and emphasis appropriately. The narrative clearly describes the data, analysis performed, insights gained, and implications."}
            }
        }
    }
]

readME = {}
readME['basic'] = {
    'num_rows': df.shape[0],
    'num_columns': df.shape[1],
    'column': list(df.columns),
    'sample_data': data,
    'missing_values': df.isnull().sum().to_dict(),
    'col_type': res_column_dtypes
}

readME['preprocessing'] = res_null_cols_reason

readME['binnable_cols_reasons'] = res_binnable_cols_reason

readME['skewness'] = {
   'left_skewed':res_left_skewed,
   'right_skewed':res_right_skewed,
   'normally_distributed':res_normally_distributed
}


# INSIGHTS FROM THE CHARTS WHICH ARE GENERATED
# visualization_data = []
# for file in os.listdir(sys.argv[1].split(".csv")[0].split("\")[-1]):
#   if file.endswith(".png"):
#     b64_image = encode_image(os.path.join(sys.argv[1].split(".csv")[0].split("\")[-1],file))
#     SYS_CONTENT = """
#     You are provided with a png file.
#     Analyze the chart and extract insights from it.
#     Give a brief description of the chart and insights extracted from it.
#     """
#     USER_CONTENT = [
#        {
#             "type": "text",
#             "text": "Analyze the chart"
#        },
#        {
#             "type": "image_url",
#             "image_url": {
#                 "url": f"data:image/png;base64,{b64_image}",
#                 "detail": "low"
#             }
#        }
#     ]
#     r = request_llm(functions,USER_CONTENT,SYS_CONTENT,"analyze_chart")
#     insights,metadata = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['extracted_insights'],json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['metadata']
#     visualization_data.append(
#        {
#             "insights":insights,
#             "metadata":metadata,
#             "file_path":file
#        }
#     )
# readME['insights'] = visualization_data





# Function to process the chart and get insights
def process_image(file_path):
    base64_image = encode_image(file_path)

    SYS_CONTENT = """
    Analyze the provided chart to extract insights.
    Provide a brief description and key insights derived from the chart.
    """
    
    USER_CONTENT = [
        {"type": "text", "text": "Analyze the chart."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "low"}},
    ]
    
    # Request insights from LLM (mocked function in this case)
    r = request_llm(functions, USER_CONTENT, SYS_CONTENT, "analyze_chart")
    insights, metadata = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['extracted_insights'],json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['metadata']
    
    return {
        "insights": insights,
        "metadata": metadata,
        "file_path": file_path
    }

# List to store visualization data
visualization_data = []

# Function to process all images using multithreading
def process_all_images(file_folder):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of file paths for all .png images
        files = [os.path.join(file_folder, file) for file in os.listdir(file_folder) if file.endswith(".png")]

        # Use map to process images in parallel
        for result in executor.map(process_image, files):
            visualization_data.append(result)

    # Assuming you want to store the results in a dictionary
    readME['insights'] = visualization_data

# Run the function to process all images
process_all_images(sys.argv[1].split(".csv")[0].split("\")[-1])
print("Images vis:",time.time() - start)



# # Create a ReadME.md file using the given data
markdown = f"# Analysis Report for `{sys.argv[1].split(".csv")[0].split("\")[-1]}`\n\n"
markdown += "## Dataset Overview\n"
markdown += f"- **Number of Rows**: {readME['basic'].get('num_rows', 'N/A')}\n"
markdown += f"- **Number of Columns**: {readME['basic'].get('num_columns', 'N/A')}\n"
markdown += f"- **Columns**:\n { readME['basic']['column'] } \n\n"

markdown += "## Sample Data\n"
markdown += f"{readME['basic'].get('sample_data', 'No sample data available')}\n\n"

markdown += "## Key Insights from Analysis\n"
markdown += "### Basic Analysis\n"
markdown += f"- **Missing Values**:\n{readME['basic']['missing_values']}\n\n"

markdown += "## Preprocessing Insights\n"
markdown += f"- **Imputing Missing Values and Reasoning**:\n{readME['preprocessing']}\n\n"

markdown += "## Binnable Columns Insights\n"
markdown += f"- **Binnable Columns and Reasoning**:\n{readME['binnable_cols_reasons']}\n\n"

markdown += "## Skewness Category\n"
markdown += f"- **Features segregation on skewness **:\n{readME['skewness']}\n\n"

markdown += "## Visualizations and Insights\n"
for entry in readME['insights']: 
    image_path = entry["file_path"]
    metadata = entry["metadata"]
    llm_response = entry["insights"]
    markdown += f"![{os.path.basename(image_path)}]({image_path})\n"
    markdown += f"- **Chart Description**: {metadata}\n"
    markdown += f"- **LLM Analysis**: {llm_response}\n\n"



# markdown += "- **Outliers**:\n"
# for outlier in insights['outliers']:
#     markdown += f"  - Column `{outlier['column']}`: {outlier['outlier_count']} outliers detected (Range: {outlier['lower_bound']} to {outlier['upper_bound']})\n"

# markdown += "### Advanced Analysis\n"
# if advanced_results.get('clustering'):
#     markdown += f"- **Clustering**: {advanced_results['clustering']}\n"
# if advanced_results.get('pca'):
#     pca_info = advanced_results['pca']
#     markdown += f"- **PCA**: Explained Variance Ratios: {pca_info['explained_variance_ratio']}\n"
# if advanced_results.get('outliers'):
#     markdown += f"- **Outliers**: {advanced_results['outliers']}\n"

# if advanced_results.get('time_series'):
#     markdown += "- **Time Series Analysis**: Time-based patterns observed. See time-series plots.\n"
# if advanced_results.get('geospatial'):
#     markdown += "- **Geospatial Analysis**: Geospatial patterns observed in the data. See geospatial plots.\n\n"

markdown += "## Recommendations and Next Steps\n"
markdown += "- **Data Quality**: Address missing values and outliers for cleaner analysis.\n"
markdown += "- **Future Exploration**: Use clustering and PCA insights for segmentation and dimensionality reduction.\n"
markdown += "- **Operational Use**: Leverage time-series patterns for forecasting and geospatial trends for targeted decision-making.\n"

SYS_CONTENT = """
Refine the markdown content to create a well-structured README.md file.  
The README should include headers, lists, and emphasis to clearly describe the data, analysis performed, insights gained, and implications.  
Use the provided markdown content as a base and improve its structure, clarity, and overall presentation.  
Ensure the final README is concise, informative, and easy to understand.
"""
USER_CONTENT = f"""
The markdown to be refined is:
{markdown}
Even include MIT License in the readME
"""
r = request_llm(functions,USER_CONTENT,SYS_CONTENT,"readME_md_creator")
readME = json.loads(r.json()['choices'][0]['message']['function_call']['arguments'])['readme_content']
with open(f"{sys.argv[1].split(".csv")[0].split("\")[-1]}/README.md","w") as f:
    f.write(readME)
print(readME)


end = time.time()

print("time: ",(end-start))
