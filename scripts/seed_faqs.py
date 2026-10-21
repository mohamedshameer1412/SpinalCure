"""Draft patient FAQs (unpublished). The doctor reads, edits and publishes them in Staff > Patient FAQs.

    DJANGO_ENV=development python scripts/seed_faqs.py

Idempotent: a question that already exists is left alone (staff edits are never overwritten).
Answers describe what the clinic does and when to see a doctor elsewhere; they make no promise of cure.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')
os.environ.setdefault('DJANGO_ENV', 'development')
import django  # noqa: E402

django.setup()
from clinic.models import FAQ, ClinicProfile, ProblemCategory  # noqa: E402

clinic = ClinicProfile.objects.first()
address = ' '.join((clinic.address or '').split()) if clinic else 'Arumbakkam, Chennai'
hours = (clinic.working_hours or '').replace('\n', '; ') if clinic else ''

# (problem name or None, question, answer)
FAQS = [
    (None, 'What is classical acupuncture?',
     'Classical acupuncture is a traditional therapy in which very fine, sterile, single-use needles are placed at '
     'specific points on the body. At Spinal Cure the doctor first examines you and asks about your history to find '
     'what is causing the pain, then plans the points for your sittings.\n\n'
     'Our approach is to treat without surgery, without medicine and without diet restrictions.'),
    (None, 'Does acupuncture hurt?',
     'The needles are much thinner than injection needles. Most people feel a light prick or a dull, heavy feeling '
     'at the point, and many relax or fall asleep during the sitting. Tell the doctor at any time if something feels '
     'uncomfortable.'),
    (None, 'How many sittings will I need?',
     'It depends on the problem, how long you have had it and how your body responds. The doctor gives you an '
     'estimate after the first examination and reviews your progress at each visit. Many treatment plans are '
     'between 5 and 15 sittings.'),
    (None, 'Do I need to stop my current medicines?',
     'Do not stop any prescribed medicine on your own. Continue as your prescribing doctor advised and tell us what '
     'you take. If your symptoms change during treatment, discuss any change in medicine with the doctor who '
     'prescribed it.'),
    (None, 'Are there food restrictions during treatment?',
     'No special diet is required for treatment at Spinal Cure. You can keep eating the food you enjoy. If you have '
     'diabetes or another condition, keep following the advice of your own doctor.'),
    (None, 'How long is one sitting?',
     'A sitting usually takes about 30 to 45 minutes, including a short check of how you have been since the last '
     'visit.'),
    (None, 'What should I bring to my first visit?',
     'Bring any scans (X-ray, MRI), recent reports and a list of the medicines you take. Wear loose, comfortable '
     'clothes so the doctor can examine the painful area.'),
    (None, 'Where is the clinic and when is it open?',
     f'Spinal Cure is at {address}.' + (f'\n\nOpening hours: {hours}.' if hours else '') +
     '\n\nPlease book an appointment before you come so we can keep a time for you.'),
    (None, 'When should I go to a hospital instead?',
     'Go to a hospital emergency department straight away if pain follows a fall or accident, or comes with '
     'weakness or numbness in the legs, loss of bladder or bowel control, fever, chest pain or sudden severe '
     'headache. These need urgent medical care first.'),
    ('Back Pain', 'Can acupuncture help long-standing lower back pain?',
     'Many of our patients come with lower back pain that has lasted months or years. The doctor examines your '
     'posture, movement and history to find the likely cause before starting. Results differ from person to '
     'person; your progress is reviewed at every sitting.'),
    ('Slip Disc', 'Can a disc bulge be treated without surgery?',
     'Many people with a disc bulge or "slip disc" manage their pain without surgery. Bring your MRI report to the '
     'first visit. If you have weakness in a leg, numbness around the groin or problems passing urine, see a spine '
     'surgeon or hospital urgently.'),
    ('Sciatica', 'What causes pain that runs down the leg?',
     'Pain from the lower back or buttock down the back of the leg is often called sciatica. It usually comes from '
     'irritation of the sciatic nerve, for example by a disc bulge or tight muscles. The doctor checks where the '
     'pain starts and how far it travels to plan treatment.'),
    ('Neck Pain', 'Why does my neck hurt after long hours on the phone or computer?',
     'Looking down for long periods strains the muscles and joints of the neck. Along with treatment, the doctor '
     'will suggest simple changes to how you sit and use screens so the pain does not keep coming back.'),
    ('Knee Pain', 'Can knee pain be treated without an operation?',
     'Knee pain has many causes, from muscle strain to wear of the joint. After examining the knee, the doctor will '
     'tell you whether acupuncture is suitable for you. If tests suggest you need a specialist opinion, we will '
     'say so.'),
    ('Frozen Shoulder', 'What is a frozen shoulder?',
     'A frozen shoulder is stiffness and pain that make it hard to lift the arm or reach behind the back. It often '
     'develops slowly. Treatment aims to ease the pain and gradually improve movement; the doctor will also show '
     'you gentle exercises for home.'),
]

added = 0
for problem_name, question, answer in FAQS:
    if FAQ.objects.filter(question=question).exists():
        continue
    problem = ProblemCategory.objects.filter(name=problem_name).first() if problem_name else None
    FAQ.objects.create(question=question, answer=answer, problem=problem, order=added, is_published=False)
    added += 1
print(f'{added} draft FAQs added (unpublished: the doctor publishes them after checking).')
