#!/usr/bin/env python3

import argparse
import csv
import os
import requests
import re
from bs4 import BeautifulSoup


# Function to make an HTTP request and retrieve HTML content
def get_html_content(link):
    url = f'https://www.bodybuilding.com{link}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    else:
        print(f"Failed to retrieve HTML content for link: https://www.bodybuilding.com{link}")
        return None

# Function to extract the type, level and description from HTML content
def extract_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract type of exercise
    type_element = soup.find('a', itemprop = "exerciseType")
    exercise_type = type_element.text.strip() if type_element else None
    
    # Extract exercise level
    level_element = soup.find('li', string = lambda text: text and 'Level:' in text)
    exercise_level = level_element.text.split('Level:')[1].strip() if level_element else None
    
    # Find the section containing the description based on the <h3> heading
    section_heading = soup.find('h3', class_ = 'ExHeading ExHeading--h3', string = lambda text: text and 'Instructions' in text)
    section = section_heading.find_next('div', class_ = 'flexo-container')

    # Extract and format description text
    description_element = section.find('div', itemprop = 'description')
    formatted_description = ''
    
    if description_element:
        # Match any description HTML tags
        description_elements = description_element.find_all(['p', 'ol', 'ul'])
        for element in description_elements:
            if element.name == 'ol':
                # Replace <ol> and <li> tags with numbered bullet points separated by newlines
                formatted_description += '\n'.join([f"{i}. {li.get_text(strip = True)}" for i, li in enumerate(element.find_all('li'), start = 1)])
            elif element.name == 'ul':
                # Replace <ul> and <li> tags with bullet points separated by newlines
                formatted_description += '\n'.join([f"• {li.get_text(strip = True)}" for li in element.find_all('li')])
            else:
                # Strip HTML tags and replace with newlines
                formatted_description += re.sub(r'<[^>]+>', '\n', str(element))
    
    return exercise_type, exercise_level, formatted_description.strip()

# Function to read HTML content from a text file
def parse_html_file(html_path):
    with open(html_path, 'r', encoding='utf-8') as file:
        html_file = file.read()
        return BeautifulSoup(html_file, 'html.parser')

# Function to find the starting point based on exercise name
def find_starting_point(soup, start_name):
    if start_name:
        start_point = soup.find('a', itemprop = 'name', string = re.compile(re.escape(start_name), re.M))
        if start_point:
            rows_to_process = start_point.find_all_next('div', class_ = 'ExResult-row')
            print(f"Picking up at '{start_name}'")
            return rows_to_process
        else:
            raise ValueError(f"Start point with '{start_name}' not found.")
    else:
        return soup.find_all('div', class_='ExResult-row')

# Function to open CSV file in append or write mode
def open_csv_file(start_name, outdir):
    if start_name:
        return open(outdir, 'a', newline='', encoding='utf-8')
    else:
        return open(outdir, 'w', newline='', encoding='utf-8')

# Function to write header row to CSV file
def write_csv_header(csv_writer):
    csv_writer.writerow(['Name', 'Muscle', 'Equipment', 'Rating', 'Type', 'Level', 'Description'])

# Function to aggregate exercise data from HTML content
def aggregate_exercise_data(soup, outdir, start_name = None):
    rows_to_process = find_starting_point(soup, start_name)

    with open_csv_file(start_name, outdir) as csv_file:
        csv_writer = csv.writer(csv_file)
        if not start_name:
            write_csv_header(csv_writer)

        # Loop over each row and get exercise details
        for exercise_row in rows_to_process:
            link = exercise_row.find('a', itemprop = 'name').get('href')
            name = exercise_row.find('a', itemprop = 'name').get_text(strip = True)
            muscle = exercise_row.find('div', class_ = 'ExResult-muscleTargeted').find('a').get_text(strip = True)
            equipment = exercise_row.find('div', class_ = 'ExResult-equipmentType').find('a').get_text(strip = True)
            rating = exercise_row.find('div', class_ = 'ExRating-badge').get_text(strip = True)

            # Make HTTP request and retrieve HTML content for each link
            html_content = get_html_content(link)

            # Extract description from HTML content
            if html_content:
                type, level, description = extract_data(html_content)
            else:
                type, level, description = None, None, None

            # Write the extracted data to the CSV file
            csv_writer.writerow([name, muscle, equipment, rating, type, level, description])

    # Close the CSV file
    csv_file.close()
    print("Data extraction and CSV creation complete.")


def parse_arguments():
    parser = argparse.ArgumentParser(description = 'Process HTML text and resume from previous exercise.')
    parser.add_argument('--html_text', type=str, help = 'HTML text of exercises to be processed', default = '../html/bodybuilding_html.txt')
    parser.add_argument('--prev_exercise', type = str, help = 'Last exercise extracted before termination', default = None)
    parser.add_argument('--output_dir', type = str, help = 'Directory to save CSV file', default = '../data/exercises_with_description.csv')
    return parser.parse_args()


def main():
    args = parse_arguments()
    html_text = args.html_text
    prev_exercise = args.prev_exercise
    outdir = args.output_dir
    
    try:
        parsed_html = parse_html_file(html_text)
        aggregate_exercise_data(parsed_html, outdir, start_name = prev_exercise)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == '__main__':
    main() 

