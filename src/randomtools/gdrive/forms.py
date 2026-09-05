"""Google Forms: the questions, and what people answered."""

from . import markdown


class Question:
    def __init__(self, question_id, title):
        self.id = question_id
        self.title = title


class Response:
    def __init__(self, response_id, respondent, submitted, answers):
        self.id = response_id
        self.respondent = respondent
        self.submitted = submitted
        self.answers = answers  # question id -> text

    @property
    def label(self):
        return self.respondent or self.id


class Form:
    def __init__(self, title, questions, responses):
        self.title = title
        self.questions = questions
        self.responses = responses

    def answer(self, response, question):
        return response.answers.get(question.id, '')


def fetch(forms_service, form_id):
    form = forms_service.forms().get(formId=form_id).execute()

    info = form.get('info', {})
    title = info.get('title') or info.get('documentTitle') or form_id

    return Form(title, questions(form), responses(forms_service, form_id))


def questions(form):
    """Flatten the form's items into the questions an answer can refer to."""

    found = []

    for item in form.get('items', []):
        title = item.get('title') or ''

        if 'questionItem' in item:
            question = item['questionItem'].get('question', {})

            if 'questionId' in question:
                found.append(Question(question['questionId'], title or '(untitled)'))

        elif 'questionGroupItem' in item:
            for question in item['questionGroupItem'].get('questions', []):
                row = question.get('rowQuestion', {}).get('title', '')

                found.append(Question(
                    question['questionId'],
                    '{} - {}'.format(title, row) if row else title or '(untitled)',
                ))

    return found


def responses(forms_service, form_id):
    found = []
    page_token = None

    while True:
        result = forms_service.forms().responses().list(
            formId=form_id,
            pageToken=page_token,
        ).execute()

        for response in result.get('responses', []):
            found.append(Response(
                response['responseId'],
                response.get('respondentEmail'),
                response.get('lastSubmittedTime') or response.get('createTime', ''),
                {
                    question_id: answer_text(answer)
                    for question_id, answer in response.get('answers', {}).items()
                },
            ))

        page_token = result.get('nextPageToken')

        if not page_token:
            break

    return found


def answer_text(answer):
    values = [
        text.get('value', '')
        for text in answer.get('textAnswers', {}).get('answers', [])
    ]

    values += [
        uploaded.get('fileName') or uploaded.get('fileId', '')
        for uploaded in answer.get('fileUploadAnswers', {}).get('answers', [])
    ]

    return ', '.join(value for value in values if value)


def header_row(form):
    return ['Submitted', 'Respondent'] + [question.title for question in form.questions]


def response_row(form, response):
    return [response.submitted, response.label] + [
        form.answer(response, question) for question in form.questions
    ]


def to_markdown(form, level=1):
    """The whole form as one document: a section per question."""

    parts = [markdown.heading(form.title, level)]

    if not form.responses:
        parts.append('*(no responses)*')

    for question in form.questions:
        parts.append(markdown.heading(question.title, level + 1))
        parts.append(answers_list(form, question))

    return '\n\n'.join(parts) + '\n'


def answers_list(form, question):
    lines = []

    for response in form.responses:
        answer = form.answer(response, question)

        if answer:
            lines.append('- **{}**: {}'.format(response.label, answer))

    return '\n'.join(lines) if lines else '*(no answers)*'


def question_markdown(form, question):
    return '{}\n\n{}\n'.format(markdown.heading(question.title), answers_list(form, question))


def person_markdown(form, response):
    parts = [markdown.heading(response.label)]

    if response.submitted:
        parts.append('*Submitted {}*'.format(response.submitted))

    for question in form.questions:
        parts.append(markdown.heading(question.title, 2))
        parts.append(form.answer(response, question) or '*(no answer)*')

    return '\n\n'.join(parts) + '\n'


def to_xlsx(form, path):
    """One sheet, a row per response - the shape Forms exports itself."""

    try:
        from openpyxl import Workbook
    except ImportError:
        raise SystemExit(
            "openpyxl is needed to write xlsx files: pip install openpyxl "
            "(or use --form-format dir / md)"
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Responses'

    sheet.append(header_row(form))

    for response in form.responses:
        sheet.append(response_row(form, response))

    workbook.save(str(path))
