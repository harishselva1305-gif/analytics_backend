import csv
import io
import logging
import os
import re
import sys
import unittest
import uuid
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
from django.conf import settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
INDEX_FILE = Path(FRONTEND_DIR, "templates", "index.html")
logger = logging.getLogger(__name__)
VERCEL_ENV = os.getenv("VERCEL_ENV", "").strip().lower()
IS_VERCEL = os.getenv("VERCEL", "").strip().lower() in {"1", "true", "yes"} or bool(VERCEL_ENV)
IS_RENDER = os.getenv("RENDER", "").strip().lower() in {"1", "true", "yes"}
IS_HOSTED = IS_VERCEL or IS_RENDER
DEBUG = os.getenv("DJANGO_DEBUG", "0" if IS_HOSTED else "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
if VERCEL_ENV == "production" or IS_RENDER:
    DEBUG = False
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-key-set-DJANGO_SECRET_KEY")

# Keep local development, all Vercel deployment URLs, and optional custom
# domains in one deduplicated setting. Vercel's host variables may be supplied
# as bare hostnames or full URLs, so parse them before passing to Django.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".vercel.app"]


def _add_allowed_host(value: str) -> None:
    value = value.strip()
    if not value:
        return
    try:
        parsed = urlsplit(value if "://" in value else f"//{value}")
        host = parsed.hostname
    except ValueError:
        return
    if host:
        host = host.lower().rstrip(".")
        if host and host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)


for configured_host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(","):
    _add_allowed_host(configured_host)

for deployment_host in (
    os.getenv("VERCEL_URL"),
    os.getenv("VERCEL_PROJECT_PRODUCTION_URL"),
    os.getenv("RENDER_EXTERNAL_HOSTNAME"),
):
    if deployment_host:
        _add_allowed_host(deployment_host)

CSRF_TRUSTED_ORIGINS = ["https://analyticsfrontend.vercel.app"]
for trusted_origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(","):
    trusted_origin = trusted_origin.strip().rstrip("/")
    if trusted_origin and trusted_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(trusted_origin)

if not DEBUG and SECRET_KEY == "development-only-key-set-DJANGO_SECRET_KEY":
    raise RuntimeError("Set DJANGO_SECRET_KEY before running MediSafe AI with DJANGO_DEBUG=0.")

settings.configure(
    BASE_DIR=BASE_DIR,
    SECRET_KEY=SECRET_KEY,
    DEBUG=DEBUG,
    ALLOWED_HOSTS=ALLOWED_HOSTS,
    CSRF_TRUSTED_ORIGINS=CSRF_TRUSTED_ORIGINS,
    WSGI_APPLICATION="wsgi.application",
    ROOT_URLCONF="backend_urls",
    INSTALLED_APPS=[
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "rest_framework",
        "backend.MediSafeConfig",
    ],
    MIGRATION_MODULES={"backend": None},
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ],
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [os.path.join(FRONTEND_DIR, "templates")],
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ]
            },
        }
    ],
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
        }
    },
    AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
        {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
        {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    ],
    DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    STATIC_URL="static/",
    CSRF_COOKIE_HTTPONLY=False,
    CSRF_COOKIE_SECURE=not DEBUG,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=not DEBUG,
    SECURE_CONTENT_TYPE_NOSNIFF=True,
    X_FRAME_OPTIONS="DENY",
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_THROTTLE_CLASSES": [
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
        ],
        "DEFAULT_THROTTLE_RATES": {"anon": "30/hour", "user": "120/hour"},
        "EXCEPTION_HANDLER": "backend.api_exception_handler",
        "TEST_REQUEST_DEFAULT_FORMAT": "json",
    },
    TEST_RUNNER="backend.ProjectTestRunner",
)

from django.apps import AppConfig, apps  # noqa: E402
from django.contrib.auth import authenticate, get_user_model, login, logout  # noqa: E402
from django.contrib.auth.decorators import login_required  # noqa: E402
from django.contrib.auth.password_validation import validate_password  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator  # noqa: E402
from django.db import DatabaseError, models, transaction  # noqa: E402
from django.db.models import Count, Q  # noqa: E402
from django.db.models.functions import TruncMonth  # noqa: E402
from django.http import HttpResponse, HttpResponseForbidden  # noqa: E402
from django.middleware.csrf import get_token  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.urls import path  # noqa: E402
from django.shortcuts import redirect, render  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.decorators import method_decorator  # noqa: E402
from django.utils.http import url_has_allowed_host_and_scheme  # noqa: E402
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie  # noqa: E402
from rest_framework import status  # noqa: E402
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated  # noqa: E402
from rest_framework.response import Response  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from rest_framework.views import APIView, exception_handler  # noqa: E402


# The models are created during AppConfig.import_models() so this single-file
# application can work with Django's app registry. Declare their module names
# here for static analyzers; _register_models() assigns the real model classes.
Medicine: Any
SymptomCategory: Any
SafetyReport: Any
ReportSymptom: Any
ReviewHistory: Any


class MediSafeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend"
    verbose_name = "MediSafe AI"

    def import_models(self):
        self.models = self.apps.all_models[self.label]
        self.models_module = sys.modules[__name__]
        _register_models()


def _register_models():
    if "medicine" in apps.all_models["backend"]:
        return

    class Medicine(models.Model):
        name = models.CharField(max_length=160, unique=True)
        is_verified = models.BooleanField(default=False)
        created_by = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            null=True,
            blank=True,
            on_delete=models.SET_NULL,
            related_name="submitted_medicines",
        )
        created_at = models.DateTimeField(auto_now_add=True)

        class Meta:
            app_label = "backend"
            ordering = ["name"]

        def __str__(self):
            return self.name

    class SymptomCategory(models.Model):
        name = models.CharField(max_length=80, unique=True)
        description = models.CharField(max_length=240, blank=True)

        class Meta:
            app_label = "backend"
            ordering = ["name"]

        def __str__(self):
            return self.name

    class SafetyReport(models.Model):
        STATUS_PENDING = "pending"
        STATUS_REVIEWED = "reviewed"
        STATUS_REJECTED = "rejected"
        STATUS_CHOICES = [
            (STATUS_PENDING, "Awaiting review"),
            (STATUS_REVIEWED, "Reviewed"),
            (STATUS_REJECTED, "Rejected"),
        ]

        report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
        user = models.ForeignKey(
            settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="safety_reports"
        )
        medicine = models.ForeignKey(
            Medicine, on_delete=models.PROTECT, related_name="safety_reports"
        )
        report_date = models.DateField()
        symptoms = models.TextField()
        duration = models.CharField(max_length=120, blank=True)
        description = models.TextField(max_length=4000)
        age_range = models.CharField(max_length=32, blank=True)
        consent = models.BooleanField(default=False)
        status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
        symptom_category = models.ForeignKey(
            SymptomCategory, null=True, blank=True, on_delete=models.SET_NULL
        )
        category_source = models.CharField(
            max_length=12,
            choices=[("predicted", "Predicted"), ("reviewed", "Reviewed")],
            default="predicted",
        )
        category_confidence = models.FloatField(null=True, blank=True)
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)

        class Meta:
            app_label = "backend"
            ordering = ["-created_at"]

    class ReportSymptom(models.Model):
        report = models.ForeignKey(
            SafetyReport, on_delete=models.CASCADE, related_name="symptom_links"
        )
        symptom_name = models.CharField(max_length=80)
        category = models.ForeignKey(SymptomCategory, on_delete=models.CASCADE)

        class Meta:
            app_label = "backend"
            constraints = [
                models.UniqueConstraint(
                    fields=["report", "symptom_name"], name="unique_report_symptom"
                )
            ]

    class ReviewHistory(models.Model):
        report = models.ForeignKey(
            SafetyReport, on_delete=models.CASCADE, related_name="review_history"
        )
        reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
        previous_status = models.CharField(max_length=16)
        new_status = models.CharField(max_length=16)
        note = models.CharField(max_length=500, blank=True)
        previous_category = models.CharField(max_length=80, blank=True)
        new_category = models.CharField(max_length=80, blank=True)
        created_at = models.DateTimeField(auto_now_add=True)

        class Meta:
            app_label = "backend"
            ordering = ["-created_at"]

    globals().update(
        Medicine=Medicine,
        SymptomCategory=SymptomCategory,
        SafetyReport=SafetyReport,
        ReportSymptom=ReportSymptom,
        ReviewHistory=ReviewHistory,
    )


SYNTHETIC_TRAINING_DATA = [
    ("nausea, vomiting, stomach upset, queasy", "Gastrointestinal"),
    ("diarrhea, loose stool, abdominal cramps", "Gastrointestinal"),
    ("constipation, bloating, indigestion, heartburn", "Gastrointestinal"),
    ("stomach pain with nausea after taking a tablet", "Gastrointestinal"),
    ("headache, migraine, head pain, pressure", "Neurological"),
    ("dizziness, lightheaded, vertigo, balance", "Neurological"),
    ("tingling, numbness, tremor, shaky hands", "Neurological"),
    ("difficulty sleeping, drowsiness, fatigue, sleepy", "Neurological"),
    ("itching, rash, hives, skin irritation", "Skin"),
    ("red skin, dry skin, swelling, skin reaction", "Skin"),
    ("acne, blister, peeling skin, localized rash", "Skin"),
    ("skin became itchy and red after taking medicine", "Skin"),
    ("shortness of breath, wheezing, coughing, tight chest", "Respiratory"),
    ("nasal congestion, sore throat, breathing difficulty", "Respiratory"),
    ("persistent cough and trouble breathing", "Respiratory"),
    ("palpitations, fast heartbeat, chest discomfort", "Cardiovascular"),
    ("high blood pressure, low blood pressure, fainting", "Cardiovascular"),
    ("irregular heartbeat, flushing, ankle swelling", "Cardiovascular"),
    ("muscle pain, joint pain, backache, cramps", "Musculoskeletal"),
    ("muscle weakness, stiff joints, body aches", "Musculoskeletal"),
    ("blurred vision, dry eyes, eye irritation", "Eye and vision"),
    ("ringing in ears, hearing changes, ear pain", "Ear and hearing"),
    ("anxiety, mood changes, confusion, agitation", "Mood and behavioral"),
    ("low mood, nervousness, unusual dreams", "Mood and behavioral"),
    ("fever, chills, sweating, feeling hot", "General"),
    ("weakness, tiredness, lack of energy, malaise", "General"),
    ("swollen face, lip swelling, tongue swelling, allergy", "Allergic reaction"),
    ("throat swelling, severe allergic response, anaphylaxis", "Allergic reaction"),
    ("reduced appetite, weight change, dry mouth", "Other"),
    ("unusual symptom that does not match other categories", "Other"),
]

_classifier = None


def api_exception_handler(exc, context):
    if isinstance(exc, DatabaseError):
        logger.error(
            "Database failure while handling an API request.",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return Response(
            {"error": "A database error occurred. Please retry the request."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data
        response.data = {"error": detail.get("detail", str(detail)) if isinstance(detail, dict) else detail}
        return response
    return None


def _error(message, code):
    return Response({"error": message}, status=code)


def _user_reports(user):
    reports = SafetyReport.objects.select_related("medicine", "symptom_category", "user")
    return reports if user.is_staff or user.is_superuser else reports.filter(user=user)


def _serialize_report(report):
    return {
        "id": str(report.report_id),
        "medicine": report.medicine.name,
        "report_date": report.report_date.isoformat(),
        "symptoms": report.symptoms,
        "duration": report.duration,
        "description": report.description,
        "age_range": report.age_range,
        "status": report.status,
        "symptom_category": report.symptom_category.name if report.symptom_category else "Unclassified",
        "category_source": report.category_source,
        "category_confidence": report.category_confidence,
        "created_at": report.created_at.isoformat(),
        "updated_at": report.updated_at.isoformat(),
        "reporter": report.user.username,
    }


def _normalize_symptoms(value):
    if isinstance(value, list):
        parts = value
    elif isinstance(value, str):
        parts = re.split(r"[,;\n]", value)
    else:
        raise ValueError("Provide symptoms as text or a list of symptom names.")
    cleaned = [str(part).strip() for part in parts if str(part).strip()]
    if not cleaned or len(cleaned) > 10 or any(len(part) > 80 for part in cleaned):
        raise ValueError("Enter between 1 and 10 symptoms, each no longer than 80 characters.")
    return ", ".join(cleaned)


def classify_symptoms(text):
    global _classifier
    normalized = (text or "").strip()
    if not normalized:
        return {
            "predicted_category": "Unclassified",
            "confidence": None,
            "method": "fallback",
            "disclaimer": "Educational classification only; this does not establish medical causation.",
        }

    if _classifier is None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
        except ImportError:
            return {
                "predicted_category": "Unclassified",
                "confidence": None,
                "method": "fallback",
                "disclaimer": "Text analysis dependencies are unavailable; no medical conclusion is made.",
            }

        training = pd.DataFrame(SYNTHETIC_TRAINING_DATA, columns=["text", "category"])
        if training["category"].nunique() < 2 or len(training) < 4:
            return {
                "predicted_category": "Unclassified",
                "confidence": None,
                "method": "fallback",
                "disclaimer": "There is insufficient synthetic training data for classification.",
            }
        _classifier = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode")),
                ("classifier", LogisticRegression(max_iter=1000, random_state=17)),
            ]
        )
        _classifier.fit(training["text"], training["category"])

    probabilities = _classifier.predict_proba([normalized])[0]
    best_index = probabilities.argmax()
    return {
        "predicted_category": str(_classifier.classes_[best_index]),
        "confidence": round(float(probabilities[best_index]), 4),
        "method": "synthetic_text_model",
        "disclaimer": "Educational classification only; this does not establish medical causation.",
    }


def _count_frame(rows, name_key, count_key="count"):
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    frame[count_key] = frame[count_key].astype(int)
    return frame.sort_values(count_key, ascending=False).rename(
        columns={name_key: "name", count_key: "count"}
    )[["name", "count"]].to_dict(orient="records")


class CsrfTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        email = str(request.data.get("email", "")).strip().lower()
        password = request.data.get("password", "")
        if not username or len(username) > 150 or not isinstance(password, str):
            return _error("A username and password are required.", status.HTTP_400_BAD_REQUEST)
        if get_user_model().objects.filter(username__iexact=username).exists():
            return _error("That username is already in use.", status.HTTP_409_CONFLICT)
        if email and get_user_model().objects.filter(email__iexact=email).exists():
            return _error("That email address is already in use.", status.HTTP_409_CONFLICT)
        try:
            validate_password(password)
        except ValidationError as exc:
            return _error(list(exc.messages), status.HTTP_400_BAD_REQUEST)
        user = get_user_model().objects.create_user(
            username=username, email=email, password=password
        )
        return Response(
            {"message": "Account created. You can now sign in."},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = request.data.get("password", "")
        if not username or not isinstance(password, str) or not password:
            return _error("Enter your username and password.", status.HTTP_400_BAD_REQUEST)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return _error("The username or password is incorrect.", status.HTTP_400_BAD_REQUEST)
        requested_role = request.data.get("role", "customer")
        if not isinstance(requested_role, str) or requested_role not in {"admin", "customer", "auto"}:
            return _error("Choose a valid account type.", status.HTTP_400_BAD_REQUEST)
        is_admin = bool(user.is_staff or user.is_superuser)
        if requested_role != "auto" and (requested_role == "admin") != is_admin:
            return _error(
                "These credentials do not match this login page.",
                status.HTTP_403_FORBIDDEN,
            )
        login(request, user)
        dashboard_url = "/admin/dashboard/" if is_admin else "/customer/dashboard/"
        next_url = request.data.get("next", "")
        if (
            isinstance(next_url, str)
            and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            )
            and (
                (is_admin and next_url.startswith(("/admin/", "/django-admin/")))
                or (not is_admin and next_url.startswith("/customer/"))
            )
        ):
            dashboard_url = next_url
        return Response(
            {
                "message": "Signed in successfully.",
                "dashboard_url": dashboard_url,
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect)
    def post(self, request):
        logout(request)
        return Response({"message": "Signed out successfully."})


class MeView(APIView):
    def get(self, request):
        return Response(
            {
                "username": request.user.username,
                "email": request.user.email,
                "is_admin": bool(request.user.is_staff or request.user.is_superuser),
            }
        )


class MedicineListView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get(self, request):
        query = str(request.query_params.get("q", "")).strip()
        medicines = Medicine.objects.all()
        if query:
            medicines = medicines.filter(name__icontains=query)
        return Response(
            {
                "results": [
                    {"id": item.id, "name": item.name, "is_verified": item.is_verified}
                    for item in medicines[:100]
                ]
            }
        )

    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = str(request.data.get("name", "")).strip()
        if not name or len(name) > 160:
            return _error("Medicine name is required and must be 160 characters or fewer.", status.HTTP_400_BAD_REQUEST)
        if Medicine.objects.filter(name__iexact=name).exists():
            return _error("A medicine with that name already exists.", status.HTTP_409_CONFLICT)
        medicine = Medicine.objects.create(name=name, is_verified=True, created_by=request.user)
        return Response(
            {"id": medicine.id, "name": medicine.name, "is_verified": medicine.is_verified},
            status=status.HTTP_201_CREATED,
        )


class ReportListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reports = _user_reports(request.user)
        query = str(request.query_params.get("q", "")).strip()
        report_status = str(request.query_params.get("status", "")).strip().lower()
        medicine = str(request.query_params.get("medicine", "")).strip()
        if query:
            reports = reports.filter(
                Q(medicine__name__icontains=query)
                | Q(symptoms__icontains=query)
                | Q(description__icontains=query)
                | Q(symptom_category__name__icontains=query)
            )
        if report_status:
            if report_status not in dict(SafetyReport.STATUS_CHOICES):
                return _error("Unknown report status.", status.HTTP_400_BAD_REQUEST)
            reports = reports.filter(status=report_status)
        if medicine:
            reports = reports.filter(medicine__name__icontains=medicine)

        paginator = Paginator(reports, 10)
        try:
            page = paginator.page(request.query_params.get("page", 1))
        except (EmptyPage, PageNotAnInteger):
            page = paginator.page(paginator.num_pages or 1)
        return Response(
            {
                "count": paginator.count,
                "page": page.number,
                "pages": paginator.num_pages,
                "results": [_serialize_report(report) for report in page.object_list],
            }
        )

    @transaction.atomic
    def post(self, request):
        medicine_name = str(request.data.get("medicine_name", "")).strip()
        description = str(request.data.get("description", "")).strip()
        report_date = request.data.get("report_date")
        age_range = str(request.data.get("age_range", "")).strip()
        duration = str(request.data.get("duration", "")).strip()
        consent = request.data.get("consent", False)
        try:
            symptoms = _normalize_symptoms(request.data.get("symptoms"))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        if not medicine_name or len(medicine_name) > 160:
            return _error("Medicine name is required and must be 160 characters or fewer.", status.HTTP_400_BAD_REQUEST)
        if not description or len(description) > 4000:
            return _error("Describe the reported experience in 1 to 4,000 characters.", status.HTTP_400_BAD_REQUEST)
        if len(duration) > 120 or len(age_range) > 32:
            return _error("Duration or age range exceeds the allowed length.", status.HTTP_400_BAD_REQUEST)
        if not isinstance(consent, bool) or not consent:
            return _error("Please confirm consent before submitting a report.", status.HTTP_400_BAD_REQUEST)
        try:
            parsed_date = date.fromisoformat(str(report_date))
            if parsed_date > timezone.localdate():
                return _error("Report date cannot be in the future.", status.HTTP_400_BAD_REQUEST)
        except (TypeError, ValueError):
            return _error("Enter a valid report date in YYYY-MM-DD format.", status.HTTP_400_BAD_REQUEST)
        if age_range and age_range not in {
            "under-18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"
        }:
            return _error("Choose one of the listed age ranges.", status.HTTP_400_BAD_REQUEST)

        medicine, _ = Medicine.objects.get_or_create(
            name=medicine_name,
            defaults={"is_verified": False, "created_by": request.user},
        )
        analysis = classify_symptoms(f"{symptoms}. {description}")
        category, _ = SymptomCategory.objects.get_or_create(
            name=analysis["predicted_category"]
        )
        report = SafetyReport.objects.create(
            user=request.user,
            medicine=medicine,
            report_date=parsed_date,
            symptoms=symptoms,
            duration=duration,
            description=description,
            age_range=age_range,
            consent=True,
            symptom_category=category,
            category_confidence=analysis["confidence"],
            category_source="predicted",
        )
        for symptom_name in symptoms.split(", "):
            ReportSymptom.objects.get_or_create(
                report=report,
                symptom_name=symptom_name,
                defaults={"category": category},
            )
        return Response(
            {"report": _serialize_report(report), "analysis": analysis},
            status=status.HTTP_201_CREATED,
        )


class ReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        report = _user_reports(request.user).filter(report_id=report_id).first()
        if report is None:
            return _error("Report not found.", status.HTTP_404_NOT_FOUND)
        return Response({"report": _serialize_report(report)})


class ReviewReportView(APIView):
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def patch(self, request, report_id):
        try:
            report = SafetyReport.objects.select_for_update().select_related("symptom_category").get(
                report_id=report_id
            )
        except SafetyReport.DoesNotExist:
            return _error("Report not found.", status.HTTP_404_NOT_FOUND)
        new_status = str(request.data.get("status", report.status)).strip().lower()
        if new_status not in {SafetyReport.STATUS_REVIEWED, SafetyReport.STATUS_REJECTED}:
            return _error("Review status must be reviewed or rejected.", status.HTTP_400_BAD_REQUEST)
        old_status = report.status
        old_category = report.symptom_category.name if report.symptom_category else ""
        category_name = str(request.data.get("symptom_category", old_category or "Unclassified")).strip()
        if not category_name or len(category_name) > 80:
            return _error("A symptom category of 1 to 80 characters is required.", status.HTTP_400_BAD_REQUEST)
        category, _ = SymptomCategory.objects.get_or_create(name=category_name)
        note = str(request.data.get("note", "")).strip()
        if len(note) > 500:
            return _error("Review note must be 500 characters or fewer.", status.HTTP_400_BAD_REQUEST)
        report.status = new_status
        report.symptom_category = category
        report.category_source = "reviewed"
        report.category_confidence = None
        report.save(
            update_fields=[
                "status", "symptom_category", "category_source", "category_confidence", "updated_at"
            ]
        )
        symptom_links = list(report.symptom_links.all())
        if symptom_links:
            report.symptom_links.update(category=category)
        else:
            for symptom_name in report.symptoms.split(", "):
                ReportSymptom.objects.get_or_create(
                    report=report,
                    symptom_name=symptom_name,
                    defaults={"category": category},
                )
        ReviewHistory.objects.create(
            report=report,
            reviewer=request.user,
            previous_status=old_status,
            new_status=new_status,
            note=note,
            previous_category=old_category,
            new_category=category.name,
        )
        return Response({"report": _serialize_report(report)})


class AnalyticsOverviewView(APIView):
    def get(self, request):
        reports = _user_reports(request.user)
        total = reports.count()
        pending = reports.filter(status=SafetyReport.STATUS_PENDING).count()
        reviewed = reports.exclude(status=SafetyReport.STATUS_PENDING).count()
        symptom_rows = list(
            reports.values(name=models.F("symptom_category__name"))
            .annotate(count=Count("report_id"))
            .order_by()
        )
        symptom_counts = _count_frame(
            [{"name": row["name"] or "Unclassified", "count": row["count"]} for row in symptom_rows],
            "name",
        )
        most_frequent = symptom_counts[0]["name"] if symptom_counts else None
        status_rows = list(reports.values("status").annotate(count=Count("report_id")).order_by())
        statuses = _count_frame(
            [{"name": row["status"], "count": row["count"]} for row in status_rows], "name"
        )
        return Response(
            {
                "total_reports": total,
                "awaiting_review": pending,
                "reviewed": reviewed,
                "most_reported_category": most_frequent,
                "status_distribution": statuses,
            }
        )


class AnalyticsMedicinesView(APIView):
    def get(self, request):
        rows = list(
            _user_reports(request.user)
            .values(name=models.F("medicine__name"))
            .annotate(count=Count("report_id"))
            .order_by()
        )
        return Response({"results": _count_frame(rows, "name")})


class AnalyticsSymptomsView(APIView):
    def get(self, request):
        rows = list(
            _user_reports(request.user)
            .values(name=models.F("symptom_category__name"))
            .annotate(count=Count("report_id"))
            .order_by()
        )
        normalized = [
            {"name": row["name"] or "Unclassified", "count": row["count"]} for row in rows
        ]
        return Response({"results": _count_frame(normalized, "name")})


class AnalyticsMonthlyView(APIView):
    def get(self, request):
        rows = list(
            _user_reports(request.user)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("report_id"))
            .order_by("month")
        )
        if not rows:
            return Response({"results": []})
        frame = pd.DataFrame(rows)
        frame["month"] = pd.to_datetime(frame["month"]).dt.strftime("%Y-%m")
        frame["count"] = frame["count"].astype(int)
        return Response(
            {
                "results": frame.rename(columns={"month": "name"})[["name", "count"]].to_dict(
                    orient="records"
                )
            }
        )


def _safe_csv(value):
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


class ReportExportView(APIView):
    def get(self, request):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "Report ID", "Medicine", "Report date", "Symptoms", "Duration",
                "Description", "Age range", "Category", "Status", "Created",
            ]
        )
        for report in _user_reports(request.user).iterator():
            writer.writerow(
                [
                    _safe_csv(report.report_id),
                    _safe_csv(report.medicine.name),
                    _safe_csv(report.report_date),
                    _safe_csv(report.symptoms),
                    _safe_csv(report.duration),
                    _safe_csv(report.description),
                    _safe_csv(report.age_range),
                    _safe_csv(report.symptom_category.name if report.symptom_category else ""),
                    _safe_csv(report.status),
                    _safe_csv(report.created_at.isoformat()),
                ]
            )
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="medisafe-reports.csv"'
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ClassifyView(APIView):
    def post(self, request):
        text = str(request.data.get("text", "")).strip()
        symptoms = request.data.get("symptoms", "")
        if isinstance(symptoms, list):
            symptoms = ", ".join(str(item) for item in symptoms)
        if not text and not str(symptoms).strip():
            return _error("Enter symptoms or a description to analyze.", status.HTTP_400_BAD_REQUEST)
        if len(text) > 4000 or len(str(symptoms)) > 1000:
            return _error("Analysis text is too long.", status.HTTP_400_BAD_REQUEST)
        return Response(
            classify_symptoms(f"{symptoms}. {text}"),
        )


@ensure_csrf_cookie
def index(request):
    return HttpResponse(INDEX_FILE.read_text(encoding="utf-8"))


def login_page(request):
    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    return render(request, "login.html", {"next": next_url})


@login_required(login_url="customer-login")
def customer_dashboard(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect("admin-dashboard")
    html = INDEX_FILE.read_text(encoding="utf-8")
    html = re.sub(
        r"\s*<!-- ADMIN_ONLY_START -->.*?<!-- ADMIN_ONLY_END -->\s*",
        "\n",
        html,
        flags=re.DOTALL,
    )
    return HttpResponse(html)


@login_required(login_url="admin-login")
def admin_dashboard(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return redirect("admin-login")
    return HttpResponse(INDEX_FILE.read_text(encoding="utf-8"))


urlpatterns = [
    path("", index, name="home"),
    path("login/", login_page, name="login-page"),
    path("customer/login/", login_page, name="customer-login"),
    path("customer/dashboard/", customer_dashboard, name="customer-dashboard"),
    path("api/csrf/", CsrfTokenView.as_view(), name="csrf-token"),
    path("api/register/", RegisterView.as_view(), name="register"),
    path("api/login/", LoginView.as_view(), name="login"),
    path("api/logout/", LogoutView.as_view(), name="logout"),
    path("api/me/", MeView.as_view(), name="me"),
    path("api/medicines/", MedicineListView.as_view(), name="medicines"),
    path("api/reports/", ReportListView.as_view(), name="reports"),
    path("api/reports/export.csv", ReportExportView.as_view(), name="report-export"),
    path("api/reports/<uuid:report_id>/", ReportDetailView.as_view(), name="report-detail"),
    path("api/reports/<uuid:report_id>/review/", ReviewReportView.as_view(), name="report-review"),
    path("api/analytics/overview/", AnalyticsOverviewView.as_view(), name="analytics-overview"),
    path("api/analytics/medicines/", AnalyticsMedicinesView.as_view(), name="analytics-medicines"),
    path("api/analytics/symptoms/", AnalyticsSymptomsView.as_view(), name="analytics-symptoms"),
    path("api/analytics/monthly/", AnalyticsMonthlyView.as_view(), name="analytics-monthly"),
    path("api/ai/classify/", ClassifyView.as_view(), name="ai-classify"),
]


class PlatformApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="reporter", password="Strong-test-pass-934!"
        )
        self.admin = get_user_model().objects.create_superuser(
            username="reviewer", email="reviewer@example.test", password="Strong-test-pass-934!"
        )
        self.client.force_authenticate(user=self.user)
        self.medicine = Medicine.objects.create(name="Example medicine", is_verified=True)
        self.category = SymptomCategory.objects.create(name="General")

    def test_registration_login_and_bad_input(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/register/",
            {"username": "newreporter", "password": "Another-strong-pass-934!"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.post("/api/login/", {"username": "newreporter", "password": "wrong"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_csrf_protected_registration_and_session_login(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/csrf/").data["csrfToken"]
        response = client.post("/api/register/", {"username": "csrfuser", "password": "Another-strong-pass-934!"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = client.post(
            "/api/register/",
            {"username": "csrfuser", "password": "Another-strong-pass-934!"},
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = client.post(
            "/api/login/",
            {"username": "csrfuser", "password": "Another-strong-pass-934!"},
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(client.get("/api/me/").data["username"], "csrfuser")

    def test_report_creation_and_required_consent(self):
        data = {
            "medicine_name": self.medicine.name,
            "report_date": timezone.localdate().isoformat(),
            "symptoms": ["headache"],
            "description": "A brief reported experience.",
            "consent": True,
        }
        response = self.client.post("/api/reports/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SafetyReport.objects.count(), 1)
        self.assertEqual(ReportSymptom.objects.count(), 1)
        data["consent"] = False
        response = self.client.post("/api/reports/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_users_cannot_access_another_users_report(self):
        other = get_user_model().objects.create_user(username="other", password="password")
        report = SafetyReport.objects.create(
            user=other,
            medicine=self.medicine,
            report_date=timezone.localdate(),
            symptoms="headache",
            description="Reported experience",
            consent=True,
        )
        response = self.client.get(f"/api/reports/{report.report_id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_only_admin_can_review(self):
        report = SafetyReport.objects.create(
            user=self.user,
            medicine=self.medicine,
            report_date=timezone.localdate(),
            symptoms="headache",
            description="Reported experience",
            consent=True,
        )
        response = self.client.patch(
            f"/api/reports/{report.report_id}/review/", {"status": "reviewed"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/reports/{report.report_id}/review/",
            {"status": "reviewed", "symptom_category": "Neurological"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.category_source, "reviewed")

    def test_empty_analytics_and_classification_fallback(self):
        response = self.client.get("/api/analytics/overview/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_reports"], 0)
        self.assertIsNone(response.data["most_reported_category"])
        response = self.client.get("/api/analytics/monthly/")
        self.assertEqual(response.data["results"], [])
        SafetyReport.objects.create(
            user=self.user,
            medicine=self.medicine,
            report_date=timezone.localdate(),
            symptoms="headache",
            description="Reported experience",
            consent=True,
            symptom_category=self.category,
        )
        overview = self.client.get("/api/analytics/overview/").data
        self.assertEqual(overview["total_reports"], 1)
        self.assertEqual(overview["awaiting_review"], 1)
        self.assertEqual(overview["most_reported_category"], "General")
        medicine_counts = self.client.get("/api/analytics/medicines/").data["results"]
        self.assertEqual(medicine_counts, [{"name": "Example medicine", "count": 1}])
        category_counts = self.client.get("/api/analytics/symptoms/").data["results"]
        self.assertEqual(category_counts, [{"name": "General", "count": 1}])
        monthly = self.client.get("/api/analytics/monthly/").data["results"]
        self.assertEqual(monthly[0]["count"], 1)
        self.assertEqual(classify_symptoms("")["predicted_category"], "Unclassified")

    def test_csv_quotes_and_formula_protection(self):
        report = SafetyReport.objects.create(
            user=self.user,
            medicine=self.medicine,
            report_date=timezone.localdate(),
            symptoms="headache",
            description="=1+1",
            consent=True,
        )
        response = self.client.get("/api/reports/export.csv")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b"'=1+1", response.content)
        self.assertIn(str(report.report_id).encode(), response.content)

    def test_authenticated_unsafe_requests_require_csrf(self):
        from rest_framework.test import APIClient

        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            "/api/ai/classify/", {"text": "headache after a tablet"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectTestRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, **kwargs):
        suite = unittest.TestSuite()
        suite.addTests(
            unittest.defaultTestLoader.loadTestsFromTestCase(PlatformApiTests)
        )
        return suite
