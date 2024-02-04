from flask import Flask, request, render_template
import pandas as pd
import numpy as np
import openai
from openai import OpenAI
from dotenv import load_dotenv
import os

app = Flask(__name__)

# Recommend top k similar items for a given item
def recommend_similar_items(similarity_matrix, item_index, item_name, threshold = 0.65, num_top = 3):
    # Use cosine similarity for recommendations
    similarities = similarity_matrix[item_index]

    # Get indices and scores of items with similarity >= threshold
    similar_indices_and_scores = [(idx, score) for idx, score in enumerate(similarities) if score >= threshold]

    # Convert to DataFrame
    result_df = pd.DataFrame(similar_indices_and_scores, columns = ['index', 'Cosine_Similarity_Score'])
    result_df['Compared_Exercise'] = item_name 

    return result_df.sort_values('Cosine_Similarity_Score', ascending = False).reset_index(drop = True).head(num_top)

# Get exercises matching user inputs
def get_exercises_from_user_inputs(df_merged, experience, muscle, types, equipment):
    has_experience = df_merged.Fitness_Experience == experience
    has_muscle = df_merged.Desired_Muscle_Groups == muscle
    has_types = df_merged.Workout_Type == types
    has_equipment = df_merged.Available_Equipment == equipment
    
    filtered_df = df_merged[has_experience & has_muscle & has_types & has_equipment]
    filtered_df = filtered_df.drop(['User_ID', 'Workout_Frequency'], axis = 1).drop_duplicates()

    # Creating a new dataframe with the specified columns
    df_selected_columns = filtered_df[['index', 'Name', 'Rating']]
    return df_selected_columns
        
# Get data of recommended exercises from user inputs
def get_exercise_recommendation(df_exercises, df_merged, similarity_matrix, experience, muscle, types, equipment):
    exercise_queries = get_exercises_from_user_inputs(df_merged, experience, muscle, types, equipment)

    ret_list = []
    for row in exercise_queries.iterrows():
        df_recommend = recommend_similar_items(similarity_matrix, row[1]['index'], row[1].Name)
        df_recommend_full = pd.merge(df_recommend, df_exercises, on = 'index')
        ret_list.append(df_recommend_full)

    ret = pd.concat(ret_list, ignore_index = True).drop_duplicates(subset = 'index', keep = 'first') # remove duplicated exercises
    return ret[['Name','Rating']].sort_values('Rating', ascending = False).head(100)

# OpenAI API connection and get chat completion
def generate_chat_completion(content):    
    try:
        client = OpenAI(api_key = os.environ.get("OPENAI_API_KEY"))
        completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        model = "gpt-4", # replace with desired model
        )
        return completion.choices[0].message.content

    except openai.APIConnectionError as e:
        print("The server could not be reached")
        print(e.__cause__)  # an underlying Exception, likely raised within httpx.
    except openai.RateLimitError as e:
        print("A 429 status code was received; we should back off a bit.")
    except openai.APIStatusError as e:
        print("Another non-200-range status code was received")
        print(e.status_code)
        print(e.response)

# Provide info given a workout split plan
def get_split_info(split):
    if split == 'Full Body Workout':
        return "Ensure the exercises target all muscle groups for every workout day."
    elif split == 'Upper/Lower Split':
        text = "Ensure upper body exercises and lower body exercises are trained on separate days. Do not combine upper body and lower body exercises for a given day. "
    elif split == 'Push/Pull Split':
        text = "Ensure push exercises and pull exercises are trained on separate days. Do not combine push and pull exercises for a given day. "
    elif split == 'Push/Pull/Legs Split':
        text = "Ensure push exercises, pull exercises and leg exercises. Do not combine push, pull or legs exercises for a given day. "
    elif split == 'Bro Split':
        text = "Ensure each individual muscle group is trained on a separate day. Do not combine multiple major muscle groups for a given day. "
    else:
        return "Determine the best workout plan given the list of exercises, either separating the days by muscle group or a combination each day."

    return text + "Avoid consecutive days that train the same split."

# Prompt template to generate workout plan
def get_prompt_template(df, experience, muscle, types, equipment, frequency, split, repeat):
    ret = f"""
    1) Formulate a one-week workout schedule following a {split} plan, where each day should consist of exactly four exercises. The schedule must include exercises for {frequency}.
    2) {get_split_info(split)}
    3) Choose exclusively {equipment} exercises and exercises categorized as {types} type and of {experience} difficulty. The exercise should focus on {muscle} muscle engagement. Exercises may include compound exercises if multiple muscle groups are specified.
    5) Allow for up to {repeat} repitition of exercises. However, no two days are exactly the same, unless in cases of 100% repetition. While for 0% repetition, select entirely different exercises with zero repeats. Prioritize highly rated exercises to repeat.
    6) Ensure all individual muscles of each muscle group provided are covered by the end of the workout schedule.
    7) The database of exercises to choose from is provided below in text format enclosed in quotations. The table includes the exercise name and rating as columns. Avoid selecting exercises with a rating of '0.0', only selecting them when options are sparse.
       "{df.to_string()}"
    8) The output format should strictly follow the structure provided below delimited by triple backticks. All brackets are placeholders and should be replaced with the specified information. If a day is dedicated as a rest day, put 'Rest Day' as the exercise name. There are no rest days for a '7 days/week' schedule.
    ```
    Day 1:
        Exercise 1: [Exercise 1 Name]
        Exercise 2: [Exercise 2 Name]
        Exercise 3: [Exercise 3 Name]
        Exercise 4: [Exercise 4 Name]
        Rationale: [Explain the specific muscle groups targeted and how the exercises fit into the overall {split} plan.]
    
    Day 2:
        [Repeat the structure for Day [1] with a different set of exercises]
    
     ...
    
    Day 7:
        [Repeat the structure for Day [1] with a different set of exercises]
    ```
    """

    return ret

# Get exercise plan using cosine similarity and OpenAI API
def generate_exercise_plan(experience, muscle, types, equipment, frequency, split, repeat):
    # Load necessary environment and data files
    load_dotenv()
    exercises_data_full = pd.read_csv("data/exercises_difficulty_classification_full.csv") # contains full exercise data with classified difficulty
    merged_data = pd.read_csv("data/merged_exercise_user_data.csv") # contains user inputs to exercise data mappings
    cosine_similarity_train = np.load("data/cosine_similarity_train.npy") # contains similarity scores between each exercise

    # Get exercise recommendations based on similarity scores
    sample_recommend = get_exercise_recommendation(exercises_data_full, merged_data, cosine_similarity_train, experience, muscle, types, equipment)

    # Get exercises schedule from OpenAI API
    template = get_prompt_template(sample_recommend, experience, muscle, types, equipment, frequency, split, repeat)
    response = generate_chat_completion(template)
    return response

# Sort and join user inputs
def sort_user_inputs(x):
    return ', '.join(sorted(x))
    
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if request.method == 'POST':
        # Extracting form data
        experience = request.form['experience']
        muscle = sort_user_inputs(request.form.getlist('muscle'))
        types = sort_user_inputs(request.form.getlist('types'))
        equipment = sort_user_inputs(request.form.getlist('equipment'))
        frequency = request.form['frequency']
        split = request.form['split'] if 'split' in request.form else ''
        repeat = request.form['repeat']
        
        # Process and generate response
        response = generate_exercise_plan(experience, muscle, types, equipment, frequency, split, repeat)
        
        # Return response
        return response

if __name__ == '__main__':
    app.run(debug=True)
