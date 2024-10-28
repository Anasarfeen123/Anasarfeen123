from flask import Flask, render_template, send_file, abort, request, jsonify
import os
import re
import logging
import configparser
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

# Database configuration (replace with your credentials)
app = Flask(__name__, template_folder='backend/templates')
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///study_data.db'
csrf = CSRFProtect(app)
db = SQLAlchemy(app)

# Model definition
class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(100), nullable=False)
    completed = db.Column(db.Boolean, nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    chapter = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<Completion {self.id}>"
    
def extract_lecture_number(filename):
# Extracts the lecture number from filenames like 'Lecture (1).pdf'.
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    return float('inf')

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Directory configurations
ROOT_DIR = r'C:\Users\Anas\OneDrive\Desktop\Study'
ICONS_DIR = os.path.join(app.static_folder, 'icons')

# File configurations
subject_icons = {
    'Maths': 'Maths_1.png',
    'Physics': 'Physics_1.png',
    'Organic Chemistry': 'Organic Chemistry_1.png',
    'Physical Chemistry': 'PC_1.png',
    'Inorganic Chemistry': 'Inorganic Chemistry_1.png',
    'Summary':'Summary_1.png',
    'Boards':'Boards_1.png'
}
forbidden_extensions = {'.tmp'}
default_icon = 'others.png'


def log_entity_existence(entity, location):
#Log a warning if an entity does not exist in the specified location.#
    logging.warning(f'No {entity} exists in {location}')


def get_pdf_completion_status(subject, grade, chapter):
#Fetch completion status for PDFs in a specific chapter.#
    completion_data = Completion.query.filter_by(
        subject=subject, grade=grade, chapter=chapter
    ).all()
    return {item.filename: item.completed for item in completion_data}


def generate_unique_id(chapter, filename):
    #Generate a unique ID for each PDF in a chapter.#
    unique_string = f"{chapter}_{filename}"
    hash_value = hash(unique_string) % 1000000# Ensure 6 digits
    return str(hash_value).zfill(6)


def store_completion(unique_id, completed, subject, grade, chapter, filename):
    #Store the completion status of a PDF.#
    completion = Completion(
        unique_id=unique_id,
        completed=completed,
        subject=subject,
        grade=grade,
        chapter=chapter,
        filename=filename
    )
    db.session.add(completion)
    db.session.commit()


def get_pdfs_and_links(subject, grade, chapter):
#Fetch PDF files and external links for a specific chapter.#
    chapter_path = os.path.join(ROOT_DIR, subject, grade, chapter)
    if not os.path.exists(chapter_path):
        logging.warning(f"Path {chapter_path} does not exist.")
        return [], []

    # List all files in the chapter folder
    files = filter_files(os.listdir(chapter_path))
    logging.info(f"Detected files in {chapter_path}: {files}")
    pdfs = [f for f in files if f.lower().endswith('.pdf')]
    
    # Extract .url files as external links
    url_files = [f for f in files if f.lower().endswith('.url')]
    external_links = extract_urls_from_files(chapter_path, url_files)
    return pdfs, external_links

def extract_urls_from_files(chapter_path, url_files):
    #Extract URLs and names from .url files without interpolation issues.#
    links = []
    for url_file in url_files:
        config = configparser.ConfigParser(interpolation=None)# Disable interpolation
        url_path = os.path.join(chapter_path, url_file)
        config.read(url_path)
        
        if 'InternetShortcut' in config and 'URL' in config['InternetShortcut']:
            url = config['InternetShortcut']['URL']
     # Use the .url filename without extension as the display name
            links.append({'name': url_file.replace('.url', ''), 'url': url})
    
    return links

def filter_files(files_list):
    #Filter out temporary and hidden files.#
    return [f for f in files_list if not f.startswith('.') and not f.endswith(tuple(forbidden_extensions))]

def get_chapter_icon(chapter):
#Fetch chapter icon based on its name.#
    cleaned_chapter_name = clean_chapter_name(chapter)
    icon_filename = f"{cleaned_chapter_name}.png"
    icon_path = os.path.join(ICONS_DIR, icon_filename)
    if os.path.exists(icon_path):
        return icon_filename
    logging.debug(f"Icon not found for {chapter}, using default.")
    return default_icon

def clean_chapter_name(chapter_name):
#Clean up chapter name by removing 'Ch'.#
    if chapter_name.startswith('Ch'):
        parts = chapter_name.split('.', 1)
        if len(parts) > 1:
            return parts[1]
    return chapter_name

@app.route('/')
def index():
#Render the index page with available subjects.#
    logging.info("Index route accessed")
    try:
        subjects = filter_files(os.listdir(ROOT_DIR))
        subjects = [s for s in subjects if os.path.isdir(os.path.join(ROOT_DIR, s))]
        return render_template('index.html', subjects=subjects, subject_icons=subject_icons, default_icon=default_icon)
    except Exception as e:
        logging.error(f"Error accessing index: {e}")
        abort(404)


@app.route('/<subject>')
def grades(subject):
#Render the grades available for a subject.#
    subject_path = os.path.join(ROOT_DIR, subject)
    if not os.path.exists(subject_path):
        logging.warning(f'{subject} does not exist.')
        abort(404)
    grades = filter_files(os.listdir(subject_path))
    grades = [g for g in grades if os.path.isdir(os.path.join(subject_path, g))]
    if not grades:
        log_entity_existence('grades', subject)
        return render_template('no_grades.html', subject=subject)
    return render_template('grades.html', subject=subject, grades=grades)


@app.route('/<subject>/<grade>')
def chapters(subject, grade):
#Render the chapters available for a specific grade in a subject.#
    grade_path = os.path.join(ROOT_DIR, subject, grade)
    if not os.path.exists(grade_path):
        logging.warning(f'{grade_path} does not exist!')
        abort(404)
    chapters = filter_files(os.listdir(grade_path))
    chapters = [c for c in chapters if os.path.isdir(os.path.join(grade_path, c))]

    def sort_key(chapter):
    #Custom sorting function for chapters.#
        try:
            parts = chapter.split('.')
            chapter_num = int(parts[0][2:]) if len(parts) > 0 and parts[0].startswith('Ch') else float('-inf')
            return (chapter_num, chapter)
        except ValueError:
            return (float('-inf'), chapter)
    chapters.sort(key=sort_key)
    cleaned_chapters = [(chapter, clean_chapter_name(chapter), get_chapter_icon(chapter)) for chapter in chapters]

    if not chapters:
        log_entity_existence('chapters', f'{subject}_{grade}')
        return render_template('no_chapters.html', subject=subject, grade=grade)
    return render_template('chapters.html', subject=subject, grade=grade, chapters=cleaned_chapters)

@app.route('/<subject>/<grade>/<chapter>')
def chapter_contents(subject, grade, chapter):
#Render the contents (PDFs, videos, URLs) of a specific chapter.#
    chapter_path = os.path.join(ROOT_DIR, subject, grade, chapter)
    if not os.path.exists(chapter_path):
        logging.warning(f'No PDFs found for {subject}, {grade}, {chapter}.')
        abort(404)
    pdfs, external_links = get_pdfs_and_links(subject, grade, chapter)
    if not pdfs and not external_links:
        log_entity_existence('PDFs and External Links', f'{subject}_{grade}_{chapter}')
        return render_template('no_files.html', subject=subject, grade=grade, chapter=chapter)

# Sort the PDFs based on the extracted lecture number
    pdfs.sort(key=extract_lecture_number)

    completion_data = get_pdf_completion_status(subject, grade, chapter)
    pdf_items = [(pdf, generate_unique_id(chapter, pdf)) for pdf in pdfs]
    completed_pdfs_count = sum(1 for pdf in pdfs if pdf in completion_data and completion_data[pdf])
    return render_template(
        'chapter.html',
        subject=subject,
        grade=grade,
        chapter=chapter,
        pdfs=pdf_items,
        urls=external_links,# Pass external links to the template
        completed_pdfs_count=completed_pdfs_count,
        total_pdfs=len(pdfs))

@app.route('/view_pdf/<subject>/<grade>/<chapter>/<filename>')
def view_pdf(subject, grade, chapter, filename):
#View a PDF file in the browser.#
    pdf_path = os.path.join(ROOT_DIR, subject, grade, chapter, filename)
    if os.path.exists(pdf_path):
        return send_file(pdf_path)
    else:
        logging.warning(f"PDF file {filename} not found in {pdf_path}.")
        abort(404)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()# Create the database tables if they don't exist
    app.run(debug=True)