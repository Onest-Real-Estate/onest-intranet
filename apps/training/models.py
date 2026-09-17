"""Training content records and governed vocabulary."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.announcements.richtext import safe_url, unsafe_links
from apps.training.embeds import validate_embed_url
from apps.training.taxonomy import (
    CERTIFICATE_STATUS_CHOICES,
    CONTENT_TYPE_CHOICES,
    INTERACTIVE_CONTENT_TYPES,
    PROGRESS_SOURCE_CHOICES,
    QUIZ_FEEDBACK_POLICY_CHOICES,
    SESSION_REGISTRATION_STATUS_CHOICES,
    SYSTEM_CATEGORY_CODES,
    VERSION_COMPLETION_POLICY_CHOICES,
    VERSION_POLICY_ANY,
    VERSION_POLICY_CURRENT,
    is_known_tool_code,
)
from apps.user.models import Office
from apps.user.storage import private_storage


class ProtectedCategoryError(Exception):
    """A category that governance does not allow to be destroyed."""


class TrainingCategoryQuerySet(models.QuerySet["TrainingCategory"]):
    def active(self) -> TrainingCategoryQuerySet:
        return self.filter(is_active=True)

    def delete(self):
        blocked = sorted(self.filter(is_system=True).values_list("code", flat=True))
        if blocked:
            raise ProtectedCategoryError(
                f"System categories cannot be deleted: {', '.join(blocked)}."
            )
        return super().delete()


class TrainingCategory(models.Model):
    code = models.SlugField(_("code"), max_length=40, unique=True)
    label = models.CharField(_("label"), max_length=80)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    is_system = models.BooleanField(_("system category"), default=False, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TrainingCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = _("training category")
        verbose_name_plural = _("training categories")

    def __str__(self):
        return self.label

    def delete(self, *args, **kwargs):
        if self.is_system or self.code in SYSTEM_CATEGORY_CODES:
            raise ProtectedCategoryError(
                f"System category {self.code!r} cannot be deleted. "
                "Deactivate it instead."
            )
        return super().delete(*args, **kwargs)


class TrainingContentQuerySet(models.QuerySet["TrainingContent"]):
    def published(self) -> TrainingContentQuerySet:
        return self.filter(status=TrainingContent.Status.PUBLISHED)

    def within_window(self, *, now=None) -> TrainingContentQuerySet:
        moment = now or timezone.now()
        return self.filter(
            Q(publish_at__isnull=True) | Q(publish_at__lte=moment),
            Q(expires_at__isnull=True) | Q(expires_at__gt=moment),
        )


class TrainingContent(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    owner_office = models.ForeignKey(
        Office,
        verbose_name=_("owning office"),
        related_name="training_content",
        on_delete=models.PROTECT,
    )
    slug = models.SlugField(_("slug"), max_length=80)
    title = models.CharField(_("title"), max_length=180)
    summary = models.CharField(_("summary"), max_length=280, blank=True)
    body = models.TextField(_("body"), blank=True)
    content_type = models.CharField(
        _("content type"),
        max_length=32,
        choices=CONTENT_TYPE_CHOICES,
    )
    category = models.ForeignKey(
        TrainingCategory,
        verbose_name=_("category"),
        related_name="content_items",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    is_required = models.BooleanField(
        _("required"),
        default=False,
        help_text=_("Required training for the matched audience."),
    )
    estimated_minutes = models.PositiveSmallIntegerField(
        _("estimated minutes"),
        null=True,
        blank=True,
    )
    tool_code = models.CharField(
        _("tool code"),
        max_length=32,
        blank=True,
        help_text=_("For tool onboarding content. Matches onboarding tool codes."),
    )
    external_url = models.CharField(
        _("external link"),
        max_length=500,
        blank=True,
        help_text=_("Optional https:// link opened in a new tab."),
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    publish_at = models.DateTimeField(_("publishes at"), null=True, blank=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    published_at = models.DateTimeField(
        _("published at"), null=True, blank=True, editable=False
    )
    archived_at = models.DateTimeField(
        _("archived at"), null=True, blank=True, editable=False
    )
    version_family = models.UUIDField(
        _("version family"),
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text=_("Shared across successive versions of the same training item."),
    )
    version_number = models.PositiveIntegerField(_("version number"), default=1)
    version_completion_policy = models.CharField(
        _("version completion policy"),
        max_length=32,
        choices=VERSION_COMPLETION_POLICY_CHOICES,
        default=VERSION_POLICY_ANY,
        help_text=_(
            "Whether required-training satisfaction needs the live version "
            f"({VERSION_POLICY_CURRENT}) or any completed version "
            f"({VERSION_POLICY_ANY})."
        ),
    )
    display_order = models.PositiveSmallIntegerField(_("display order"), default=100)
    created_by = models.ForeignKey(
        "user.User",
        verbose_name=_("created by"),
        related_name="training_content_created",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    updated_by = models.ForeignKey(
        "user.User",
        verbose_name=_("last edited by"),
        related_name="training_content_edited",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TrainingContentQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name = _("training content")
        verbose_name_plural = _("training content")
        constraints = [
            models.UniqueConstraint(
                fields=["owner_office", "slug"],
                name="training_content_unique_slug_per_office",
            ),
            models.CheckConstraint(
                condition=~Q(status="published") | Q(category__isnull=False),
                name="training_published_requires_category",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True)
                | Q(publish_at__isnull=True)
                | Q(expires_at__gt=F("publish_at")),
                name="training_window_ordered",
            ),
            models.UniqueConstraint(
                fields=["version_family", "version_number"],
                name="training_content_unique_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "is_required", "display_order"],
                name="training_library_order",
            ),
            models.Index(
                fields=["status", "content_type"],
                name="training_status_type",
            ),
            models.Index(
                fields=["version_family", "version_number"],
                name="training_version_family",
            ),
        ]

    def __str__(self):
        return f"{self.owner_office} / {self.slug}"

    @property
    def scope_level(self) -> str:
        if self.owner_office.kind == Office.Kind.HEAD_OFFICE:
            return "company"
        if self.owner_office.kind == Office.Kind.REGION:
            return "region"
        return "office"

    @property
    def is_interactive(self) -> bool:
        return self.content_type in INTERACTIVE_CONTENT_TYPES

    def is_visible_at(self, moment) -> bool:
        if self.status != self.Status.PUBLISHED:
            return False
        if self.publish_at is not None and self.publish_at > moment:
            return False
        return self.expires_at is None or self.expires_at > moment

    def clean(self):
        super().clean()
        from apps.training.services import validation_debt

        errors: dict[str, object] = {}
        if self.expires_at and self.publish_at and self.expires_at <= self.publish_at:
            errors["expires_at"] = _("Expiry must be after the publish time.")
        if self.external_url and safe_url(self.external_url) is None:
            errors["external_url"] = _(
                "Use an https:// address, a mailto: address, or a hub path "
                "starting with /."
            )
        refused = unsafe_links(self.body)
        if refused:
            errors["body"] = _(
                "These links are not allowed: %(links)s. Use https://, "
                "mailto:, or a hub path starting with /."
            ) % {"links": ", ".join(refused[:3])}
        if self.tool_code and not is_known_tool_code(self.tool_code):
            errors["tool_code"] = _("Unknown tool code.")
        if (
            self.category is not None
            and not self.category.is_active
            and self._category_changed()
        ):
            errors["category"] = _("That category is retired. Choose an active one.")
        if self.status == self.Status.PUBLISHED:
            for field, message in validation_debt(self):
                errors.setdefault(field, message)
        if errors:
            raise ValidationError(errors)

    def _category_changed(self) -> bool:
        if not self.pk:
            return True
        previous = (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("category__code", flat=True)
            .first()
        )
        return previous != (self.category.code if self.category else None)


class TrainingAudience(models.Model):
    class Kind(models.TextChoices):
        COMPANY = "company", _("Everyone at the brokerage")
        ROLE = "role", _("Everyone holding a role")
        REGION = "region", _("A region and the offices under it")
        OFFICE = "office", _("One office only")
        USER = "user", _("One named person")

    content = models.ForeignKey(
        TrainingContent,
        verbose_name=_("content"),
        related_name="audiences",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices)
    role = models.CharField(_("role code"), max_length=64, blank=True)
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="training_audiences",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("person"),
        related_name="training_audiences",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("training audience")
        verbose_name_plural = _("training audiences")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="company", role="", office__isnull=True, user__isnull=True)
                    | (
                        Q(kind="role", office__isnull=True, user__isnull=True)
                        & ~Q(role="")
                    )
                    | Q(
                        kind__in=["region", "office"],
                        role="",
                        office__isnull=False,
                        user__isnull=True,
                    )
                    | Q(kind="user", role="", office__isnull=True, user__isnull=False)
                ),
                name="training_audience_one_target_per_kind",
            ),
            models.UniqueConstraint(
                fields=["content"],
                condition=Q(kind="company"),
                name="training_audience_one_company_row",
            ),
            models.UniqueConstraint(
                fields=["content", "role"],
                condition=Q(kind="role"),
                name="training_audience_unique_role",
            ),
            models.UniqueConstraint(
                fields=["content", "kind", "office"],
                condition=Q(office__isnull=False),
                name="training_audience_unique_office",
            ),
            models.UniqueConstraint(
                fields=["content", "user"],
                condition=Q(kind="user"),
                name="training_audience_unique_user",
            ),
        ]
        indexes = [
            models.Index(fields=["kind", "office"], name="training_aud_office"),
            models.Index(fields=["kind", "role"], name="training_aud_role"),
            models.Index(fields=["kind", "user"], name="training_aud_user"),
        ]


class TrainingEmbed(models.Model):
    content = models.OneToOneField(
        TrainingContent,
        verbose_name=_("content"),
        related_name="embed",
        on_delete=models.CASCADE,
    )
    url = models.CharField(_("embed URL"), max_length=500)
    provider = models.CharField(_("provider"), max_length=32)
    host = models.CharField(_("host"), max_length=120)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training embed")
        verbose_name_plural = _("training embeds")

    def clean(self):
        super().clean()
        parsed = validate_embed_url(self.url)
        self.provider = parsed.provider
        self.host = parsed.host


class TrainingTranscription(models.Model):
    content = models.OneToOneField(
        TrainingContent,
        verbose_name=_("content"),
        related_name="transcription",
        on_delete=models.CASCADE,
    )
    segments = models.JSONField(
        _("segments"),
        default=list,
        help_text=_("List of {startMs, endMs, text} objects."),
    )
    search_text = models.TextField(_("search text"), blank=True, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training transcription")
        verbose_name_plural = _("training transcriptions")

    def rebuild_search_text(self) -> None:
        parts = []
        for segment in self.segments or []:
            if isinstance(segment, dict):
                text = str(segment.get("text", "")).strip()
                if text:
                    parts.append(text)
        self.search_text = " ".join(parts)


def _media_upload_to(instance, filename):
    from apps.training.media import storage_key

    return storage_key(filename)


class TrainingMediaQuerySet(models.QuerySet["TrainingMedia"]):
    def readable(self) -> TrainingMediaQuerySet:
        return self.filter(
            is_active=True,
            processing_state=TrainingMedia.ProcessingState.READY,
        )


class TrainingMedia(models.Model):
    class Role(models.TextChoices):
        PRIMARY = "primary", _("Primary media")
        ATTACHMENT = "attachment", _("Attachment")

    class ProcessingState(models.TextChoices):
        PENDING = "pending", _("Processing")
        READY = "ready", _("Ready")
        QUARANTINED = "quarantined", _("Quarantined")
        FAILED = "failed", _("Processing failed")

    content = models.ForeignKey(
        TrainingContent,
        verbose_name=_("content"),
        related_name="media",
        on_delete=models.CASCADE,
    )
    role = models.CharField(_("role"), max_length=16, choices=Role.choices)
    display_name = models.CharField(_("display name"), max_length=180)
    file = models.FileField(
        _("file"),
        max_length=255,
        storage=private_storage,
        upload_to=_media_upload_to,
    )
    media_type = models.CharField(_("media type"), max_length=120)
    byte_size = models.PositiveBigIntegerField(_("size in bytes"))
    checksum = models.CharField(_("checksum"), max_length=64)
    processing_state = models.CharField(
        _("processing state"),
        max_length=16,
        choices=ProcessingState.choices,
        default=ProcessingState.PENDING,
    )
    processing_note = models.CharField(_("processing note"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    uploaded_by = models.ForeignKey(
        "user.User",
        verbose_name=_("uploaded by"),
        related_name="training_media_uploaded",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = TrainingMediaQuerySet.as_manager()

    class Meta:
        ordering = ["role", "sort_order", "pk"]
        verbose_name = _("training media")
        verbose_name_plural = _("training media")
        constraints = [
            models.UniqueConstraint(
                fields=["content"],
                condition=Q(role="primary", is_active=True),
                name="training_one_active_primary",
            ),
            models.CheckConstraint(
                condition=Q(byte_size__gt=0), name="training_media_has_bytes"
            ),
        ]

    @property
    def is_readable(self) -> bool:
        return self.is_active and self.processing_state == self.ProcessingState.READY


class TrainingModule(models.Model):
    course = models.ForeignKey(
        TrainingContent,
        verbose_name=_("course"),
        related_name="modules",
        on_delete=models.CASCADE,
    )
    child = models.ForeignKey(
        TrainingContent,
        verbose_name=_("module"),
        related_name="parent_courses",
        on_delete=models.CASCADE,
    )
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = _("training module")
        verbose_name_plural = _("training modules")
        constraints = [
            models.UniqueConstraint(
                fields=["course", "child"],
                name="training_module_unique_child",
            ),
        ]


class TrainingProgress(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")

    class Source(models.TextChoices):
        LEARNER = "learner", _("Learner")
        QUIZ = "quiz", _("Quiz")
        SESSION = "session", _("Live session")
        COURSE_ROLLUP = "course_rollup", _("Course rollup")
        ADMIN_CORRECTION = "admin_correction", _("Admin correction")
        SYSTEM = "system", _("System")

    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="training_progress",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        TrainingContent,
        verbose_name=_("content"),
        related_name="progress_records",
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    progress_percent = models.PositiveSmallIntegerField(
        _("progress percent"),
        null=True,
        blank=True,
    )
    content_version_number = models.PositiveIntegerField(
        _("content version number"),
        null=True,
        blank=True,
    )
    is_required_at_completion = models.BooleanField(
        _("required at completion"),
        null=True,
        blank=True,
    )
    source = models.CharField(
        _("source"),
        max_length=32,
        choices=PROGRESS_SOURCE_CHOICES,
        default=Source.SYSTEM,
        blank=True,
    )
    evidence = models.JSONField(_("evidence"), default=dict, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training progress")
        verbose_name_plural = _("training progress")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content"],
                name="training_progress_unique_user_content",
            ),
            models.CheckConstraint(
                condition=Q(progress_percent__isnull=True)
                | (Q(progress_percent__gte=0) & Q(progress_percent__lte=100)),
                name="training_progress_percent_range",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="training_progress_user"),
            models.Index(
                fields=["content", "status"], name="training_progress_content"
            ),
        ]


class TrainingQuiz(models.Model):
    class FeedbackPolicy(models.TextChoices):
        NONE = "none", _("No feedback")
        SCORE_ONLY = "score_only", _("Score only")
        REVIEW = "review", _("Score and review")

    content = models.OneToOneField(
        TrainingContent,
        verbose_name=_("content"),
        related_name="quiz",
        on_delete=models.CASCADE,
    )
    pass_threshold_percent = models.PositiveSmallIntegerField(
        _("pass threshold percent"),
        default=80,
    )
    max_attempts = models.PositiveSmallIntegerField(
        _("max attempts"),
        null=True,
        blank=True,
        help_text=_("Leave blank for unlimited attempts."),
    )
    feedback_policy = models.CharField(
        _("feedback policy"),
        max_length=16,
        choices=QUIZ_FEEDBACK_POLICY_CHOICES,
        default=FeedbackPolicy.SCORE_ONLY,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training quiz")
        verbose_name_plural = _("training quizzes")
        constraints = [
            models.CheckConstraint(
                condition=Q(pass_threshold_percent__gte=0)
                & Q(pass_threshold_percent__lte=100),
                name="training_quiz_threshold_range",
            ),
        ]


class TrainingQuizQuestion(models.Model):
    quiz = models.ForeignKey(
        TrainingQuiz,
        verbose_name=_("quiz"),
        related_name="questions",
        on_delete=models.CASCADE,
    )
    prompt = models.CharField(_("prompt"), max_length=500)
    choices = models.JSONField(
        _("choices"),
        default=list,
        help_text=_("List of {id, label} objects."),
    )
    correct_choice_ids = models.JSONField(
        _("correct choice ids"),
        default=list,
        help_text=_("Server-only. Never serialize to learners."),
    )
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = _("training quiz question")
        verbose_name_plural = _("training quiz questions")


class TrainingQuizAttempt(models.Model):
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="training_quiz_attempts",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        TrainingContent,
        verbose_name=_("content"),
        related_name="quiz_attempts",
        on_delete=models.CASCADE,
    )
    attempt_number = models.PositiveSmallIntegerField(_("attempt number"))
    answers = models.JSONField(_("answers"), default=dict)
    score_percent = models.PositiveSmallIntegerField(_("score percent"))
    passed = models.BooleanField(_("passed"), default=False)
    submitted_at = models.DateTimeField(_("submitted at"), auto_now_add=True)
    content_version_number = models.PositiveIntegerField(_("content version number"))

    class Meta:
        verbose_name = _("training quiz attempt")
        verbose_name_plural = _("training quiz attempts")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content", "attempt_number"],
                name="training_quiz_attempt_unique",
            ),
            models.CheckConstraint(
                condition=Q(score_percent__gte=0) & Q(score_percent__lte=100),
                name="training_quiz_score_range",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "content"], name="training_quiz_attempt_user"),
        ]


class TrainingLiveSession(models.Model):
    content = models.OneToOneField(
        TrainingContent,
        verbose_name=_("content"),
        related_name="live_session",
        on_delete=models.CASCADE,
    )
    starts_at = models.DateTimeField(_("starts at"))
    timezone = models.CharField(
        _("timezone"),
        max_length=64,
        default="America/New_York",
        help_text=_("IANA timezone for display."),
    )
    duration_minutes = models.PositiveSmallIntegerField(
        _("duration minutes"),
        default=60,
    )
    capacity = models.PositiveIntegerField(
        _("capacity"),
        null=True,
        blank=True,
        help_text=_("Leave blank for unlimited capacity."),
    )
    meeting_url = models.CharField(_("meeting URL"), max_length=500, blank=True)
    registration_opens_at = models.DateTimeField(
        _("registration opens at"),
        null=True,
        blank=True,
    )
    registration_closes_at = models.DateTimeField(
        _("registration closes at"),
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training live session")
        verbose_name_plural = _("training live sessions")


class TrainingSessionRegistration(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "registered", _("Registered")
        CANCELLED = "cancelled", _("Cancelled")
        ATTENDED = "attended", _("Attended")
        NO_SHOW = "no_show", _("No show")

    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="training_session_registrations",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        TrainingContent,
        verbose_name=_("content"),
        related_name="session_registrations",
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=SESSION_REGISTRATION_STATUS_CHOICES,
        default=Status.REGISTERED,
    )
    registered_at = models.DateTimeField(_("registered at"), auto_now_add=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    attended_at = models.DateTimeField(_("attended at"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training session registration")
        verbose_name_plural = _("training session registrations")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content"],
                name="training_session_reg_unique_user",
            ),
        ]
        indexes = [
            models.Index(
                fields=["content", "status"], name="training_session_reg_status"
            ),
        ]


def _certificate_upload_to(instance, filename):
    from apps.training.media import storage_key

    return storage_key(filename, prefix="certificates")


class TrainingCertificate(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REVOKED = "revoked", _("Revoked")

    public_id = models.UUIDField(
        _("public id"),
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text=_("Opaque id embedded in the certificate QR for verification."),
    )
    user = models.ForeignKey(
        "user.User",
        verbose_name=_("user"),
        related_name="training_certificates",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        TrainingContent,
        verbose_name=_("content"),
        related_name="certificates",
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=CERTIFICATE_STATUS_CHOICES,
        default=Status.PENDING,
    )
    file = models.FileField(
        _("file"),
        max_length=255,
        storage=private_storage,
        upload_to=_certificate_upload_to,
        blank=True,
    )
    signature = models.CharField(
        _("signature"),
        max_length=128,
        blank=True,
        help_text=_("HMAC-SHA256 hex digest of the canonical certificate payload."),
    )
    signature_algorithm = models.CharField(
        _("signature algorithm"),
        max_length=32,
        blank=True,
        default="",
        help_text=_("e.g. hmac-sha256-v1"),
    )
    approved_by = models.ForeignKey(
        "user.User",
        verbose_name=_("approved by"),
        related_name="training_certificates_approved",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("training certificate")
        verbose_name_plural = _("training certificates")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content"],
                name="training_certificate_unique_user",
            ),
        ]
