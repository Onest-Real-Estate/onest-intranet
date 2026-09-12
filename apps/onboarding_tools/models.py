"""The agent tool catalog, and each agent's progress through it.

The list of tools a new agent needs used to be four values in a ``TextChoices``
enum. That shape cannot express this catalog: it is roughly two dozen tools in
three groups, it changes when a vendor does, and the MLS and association
entries **depend on where the agent works** — SmartMLS and CT Realtors belong to
Connecticut, and an agent in Virginia needs neither. Every one of those facts
would otherwise be a deploy.

So the catalog is data, modelled on ``web.QuickAccessLink``, which learned the
same lesson: a tool is company-wide, or it names the offices and regions it
applies to, and resolution walks the office tree.

The second thing that makes this catalog useful rather than a list of names is
that **every tool says how to get it**. A self-serve tool carries the steps to
create the account; a provisioned one names who at oNEST turns it on. A
checklist that tells somebody they need HiHello without telling them how to get
it has moved the problem, not solved it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.user.models import Office


class ToolGroup(models.TextChoices):
    """The three shelves the catalog is read on.

    Groups are presentation, but they are stored rather than derived: an agent
    reads "what do I still need for marketing" far more often than they read
    the whole list, and the grouping is the product's, not a category the code
    can infer from a vendor name.
    """

    COMPANY = "company", _("Company tools")
    ASSOCIATION = "association", _("Association & MLS")
    MARKETING = "marketing", _("Profiles & marketing")


class Provisioning(models.TextChoices):
    """Who actually creates the account.

    This is the fork the whole guide hangs off: a self-serve tool needs steps
    the agent can follow now, and a provisioned one needs a name to chase.
    Getting it wrong in either direction wastes somebody's morning.
    """

    SELF_SERVE = "self_serve", _("You set this up")
    ONEST = "onest", _("oNEST sets this up for you")
    #: Agent signs up, oNEST then has to approve or link the account.
    BOTH = "both", _("You sign up, then oNEST activates it")


class ToolQuerySet(models.QuerySet["OnboardingTool"]):
    def live(self) -> ToolQuerySet:
        return self.filter(is_active=True)

    def for_office(self, office: Office | None) -> ToolQuerySet:
        """Tools that apply where this agent works.

        Company-wide tools always apply. The rest are matched against the
        office's own ancestry, so a row on a region with descendants included
        covers every branch beneath it without one row per branch.

        An agent with no office yet sees only the company-wide set: guessing an
        association from a blank field would tell somebody to join the wrong
        MLS.
        """
        if office is None:
            return self.live().filter(company_wide=True)

        from apps.user.services.hierarchy import ancestor_ids

        # The office itself plus everything above it: a row on Connecticut with
        # descendants included has to match an agent sitting in a branch under
        # it, which is the whole point of the flag.
        chain = {office.pk, *ancestor_ids(office)}
        applies = Q(company_wide=True)
        applies |= Q(
            office_audiences__office_id=office.pk,
        )
        applies |= Q(
            office_audiences__office_id__in=sorted(chain),
            office_audiences__include_descendants=True,
        )
        return self.live().filter(applies).distinct()


class OnboardingTool(models.Model):
    """One account or app an agent needs, and how to get it."""

    slug = models.SlugField(_("slug"), max_length=60, unique=True)
    name = models.CharField(_("name"), max_length=80)
    #: One line, shown under the name. What the tool is *for*, in the agent's
    #: terms — "transaction documents and signatures", not "SaaS platform".
    description = models.CharField(_("description"), max_length=200)
    group = models.CharField(_("group"), max_length=20, choices=ToolGroup.choices)
    provisioning = models.CharField(
        _("provisioning"),
        max_length=16,
        choices=Provisioning.choices,
        default=Provisioning.ONEST,
    )

    #: Where the agent goes once they have the account. Validated as https by
    #: the form; never rendered as a link when blank.
    open_url = models.URLField(_("open url"), max_length=500, blank=True)
    #: The vendor's own help page, when there is a good one.
    help_url = models.URLField(_("vendor help url"), max_length=500, blank=True)

    #: The walkthrough. An ordered list of plain strings — deliberately not
    #: rich text: these are steps somebody follows on a second monitor, and a
    #: format that allows headings and images invites a manual instead.
    setup_steps = models.JSONField(_("setup steps"), default=list, blank=True)
    #: Who to chase when the agent cannot do it themselves. Free text on
    #: purpose: this is "your branch admin" or "IT support" as often as it is a
    #: named person, and modelling it as a user would break the moment somebody
    #: leaves.
    contact_label = models.CharField(_("who to contact"), max_length=120, blank=True)
    #: Optional deep link to the request that starts it — usually the IT
    #: support form. Stored as a path so it survives a domain change.
    request_path = models.CharField(_("request path"), max_length=200, blank=True)

    company_wide = models.BooleanField(
        _("applies everywhere"),
        default=True,
        help_text=_(
            "Off means this tool applies only to the offices and regions named "
            "below — an MLS or a state association, typically."
        ),
    )
    #: Whether an agent is expected to have it at all. A tool that is merely
    #: available should not make somebody's checklist read as incomplete.
    is_required = models.BooleanField(_("required"), default=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveIntegerField(_("sort order"), default=0)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = ToolQuerySet.as_manager()

    class Meta:
        ordering = ["group", "sort_order", "name"]
        verbose_name = _("onboarding tool")
        verbose_name_plural = _("onboarding tools")
        constraints = [
            models.CheckConstraint(
                condition=~Q(name=""), name="onboarding_tool_requires_name"
            ),
            # A tool nobody can act on is a dead row on a checklist: either the
            # agent can follow steps, or there is somebody to chase.
            models.CheckConstraint(
                condition=~(Q(setup_steps=[]) & Q(contact_label="")),
                name="onboarding_tool_needs_steps_or_a_contact",
            ),
        ]
        indexes = [
            models.Index(
                fields=["group", "sort_order"], name="onbtool_group_order_idx"
            ),
            models.Index(fields=["is_active"], name="onbtool_active_idx"),
        ]

    if TYPE_CHECKING:
        # The reverse accessor Django creates from
        # ``OnboardingToolOfficeAudience.tool``. Declared so the checker can
        # see it, the same way the rest of this project does.
        from django.db.models.manager import RelatedManager

        office_audiences: RelatedManager[OnboardingToolOfficeAudience]

    def __str__(self) -> str:
        return self.name

    @property
    def is_self_serve(self) -> bool:
        return self.provisioning in {Provisioning.SELF_SERVE, Provisioning.BOTH}


class OnboardingToolOfficeAudience(models.Model):
    """One office-tree node a location-specific tool applies to.

    ``include_descendants`` is what makes a region or state expressible without
    a row per branch: SmartMLS attaches once to the Connecticut node and covers
    every office beneath it.
    """

    tool = models.ForeignKey(
        OnboardingTool,
        verbose_name=_("tool"),
        related_name="office_audiences",
        on_delete=models.CASCADE,
    )
    office = models.ForeignKey(
        Office,
        verbose_name=_("office"),
        related_name="onboarding_tool_audiences",
        on_delete=models.CASCADE,
    )
    include_descendants = models.BooleanField(_("include descendants"), default=True)

    if TYPE_CHECKING:
        tool_id: int
        office_id: int

    class Meta:
        ordering = ["office__sort_order", "office__name"]
        verbose_name = _("onboarding tool audience")
        verbose_name_plural = _("onboarding tool audiences")
        constraints = [
            models.UniqueConstraint(
                fields=["tool", "office"], name="onboarding_tool_audience_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.tool} @ {self.office}"


class ToolState(models.TextChoices):
    """Where one agent is with one tool.

    ``REQUESTED`` and ``INVITATION_SENT`` exist because "in progress" could not
    answer the one question activation depends on: *has the office actually
    sent this agent their vendor invitation, and when?* A free-text note cannot
    be queried, and audit history is not a state machine.

    ``NOT_APPLICABLE`` exists so a branch can switch a tool off for one person
    without deleting the row and losing who decided that.
    """

    NOT_STARTED = "not_started", _("Not started")
    REQUESTED = "requested", _("Requested")
    INVITATION_SENT = "invitation_sent", _("Invitation sent")
    IN_PROGRESS = "in_progress", _("In progress")
    READY = "ready", _("Ready")
    BLOCKED = "blocked", _("Blocked")
    NOT_APPLICABLE = "not_applicable", _("Not needed")


#: States that count toward "ready". Used by the progress figure and the group
#: headers — one definition, so a count and a bar cannot disagree.
COMPLETE_STATES: frozenset[str] = frozenset({ToolState.READY, ToolState.NOT_APPLICABLE})

#: Settled either way: the agent is not waiting on anybody.
SETTLED_STATES: frozenset[str] = COMPLETE_STATES

#: Still outstanding. The New Agent List keeps a record while any tool is here.
OPEN_STATES: frozenset[str] = frozenset(
    {
        ToolState.NOT_STARTED,
        ToolState.REQUESTED,
        ToolState.INVITATION_SENT,
        ToolState.IN_PROGRESS,
        ToolState.BLOCKED,
    }
)

#: The forward order of a normal setup. Skipping ahead is ordinary — a
#: self-serve tool goes straight to ready — but moving *back* down this ladder
#: is a correction, and :func:`services.set_state` demands a reason for it.
STATE_ORDER: tuple[str, ...] = (
    ToolState.NOT_STARTED,
    ToolState.REQUESTED,
    ToolState.INVITATION_SENT,
    ToolState.IN_PROGRESS,
    ToolState.READY,
)

#: States only meaningful when somebody at oNEST provisions the seat. Nobody
#: sends an invitation for a tool the agent signs up for themselves.
PROVISIONED_ONLY_STATES: frozenset[str] = frozenset(
    {ToolState.REQUESTED, ToolState.INVITATION_SENT}
)


def invitation_presentation(*, provisioning: str, invitation_sent_at) -> dict[str, str]:
    """How the invitation reads, in one place for every surface.

    Values mirror the journey contract's invitation states so the agent's own
    page, the operational list, and the dashboard cannot describe the same row
    differently.
    """
    if provisioning == Provisioning.SELF_SERVE:
        return {"state": "not_applicable", "label": "You set this one up yourself"}
    if invitation_sent_at is not None:
        return {"state": "sent", "label": "Invitation sent"}
    return {"state": "pending", "label": "Waiting on your office"}


class AgentToolStatusQuerySet(models.QuerySet["AgentToolStatus"]):
    def for_reader(self, user, *, access) -> AgentToolStatusQuerySet:
        """Whose progress this reader may see.

        Everybody sees their own. Beyond that it is the ordinary office-tree
        reach: a branch manager sees their branch, a regional sees their
        region, an administrator sees the brokerage. There is no separate
        grant — if you may already see the agent in the directory, you may see
        whether their email works.
        """
        if getattr(user, "is_anonymous", False):
            return self.none()

        mine = Q(agent=user)
        if getattr(user, "is_superuser", False) or access.company_wide:
            return self.all()

        reach = Q(pk__in=[])
        if access.office_keys:
            reach |= Q(agent__office__stable_key__in=sorted(access.office_keys))
        if access.region_keys:
            reach |= Q(agent__office__region__stable_key__in=sorted(access.region_keys))
        return self.filter(reach | mine).distinct()


class AgentToolStatus(models.Model):
    """One agent's state on one tool.

    Rows are created lazily: a tool with no row is simply "not started", so
    adding a tool to the catalog does not require writing a row for every agent
    in the brokerage.
    """

    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tool_statuses",
        verbose_name=_("agent"),
    )
    tool = models.ForeignKey(
        OnboardingTool,
        on_delete=models.CASCADE,
        related_name="agent_statuses",
        verbose_name=_("tool"),
    )
    state = models.CharField(
        _("state"),
        max_length=20,
        choices=ToolState.choices,
        default=ToolState.NOT_STARTED,
    )
    #: Free text from whoever moved it — "waiting on the vendor", "agent has
    #: the invite". Never shown outside the reader's own scope.
    note = models.CharField(_("note"), max_length=300, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="updated_tool_statuses",
        verbose_name=_("updated by"),
    )
    #: Invitation provenance as structured columns rather than a note or an
    #: audit scrape: "has the office sent this agent their Lofty invitation,
    #: and when" has to be answerable in a query, and training unlocks on it.
    requested_at = models.DateTimeField(_("requested at"), null=True, blank=True)
    invitation_sent_at = models.DateTimeField(
        _("invitation sent at"), null=True, blank=True
    )
    invitation_sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_tool_invitations",
        verbose_name=_("invitation sent by"),
    )
    ready_at = models.DateTimeField(_("ready at"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = AgentToolStatusQuerySet.as_manager()

    class Meta:
        ordering = ["tool__group", "tool__sort_order"]
        verbose_name = _("agent tool status")
        verbose_name_plural = _("agent tool statuses")
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "tool"], name="agent_tool_status_unique"
            ),
            # Ready and a readiness timestamp travel together, so any figure
            # that asks "when did this agent become workable" has one answer.
            models.CheckConstraint(
                condition=(
                    Q(state="ready", ready_at__isnull=False)
                    | (~Q(state="ready") & Q(ready_at__isnull=True))
                ),
                name="agent_tool_ready_at_matches_state",
            ),
            # A named sender without a time is provenance nobody can use. The
            # reverse is allowed: the sender's account may be deleted later,
            # and losing the name must not erase the fact it was sent.
            models.CheckConstraint(
                condition=(
                    Q(invitation_sent_by__isnull=True)
                    | Q(invitation_sent_at__isnull=False)
                ),
                name="agent_tool_invitation_sender_has_time",
            ),
            # "Invitation sent" with no timestamp is exactly the ambiguity this
            # lifecycle exists to remove.
            models.CheckConstraint(
                condition=(
                    ~Q(state="invitation_sent") | Q(invitation_sent_at__isnull=False)
                ),
                name="agent_tool_invitation_sent_has_time",
            ),
        ]
        indexes = [
            models.Index(fields=["agent", "state"], name="agenttool_agent_state_idx"),
            models.Index(fields=["tool", "state"], name="agenttool_tool_state_idx"),
        ]

    if TYPE_CHECKING:
        # Django generates these at runtime; declaring them here is how the
        # rest of this project keeps the checker honest about a relation's id
        # column without dereferencing the relation.
        agent_id: int
        tool_id: int

    def __str__(self) -> str:
        return f"{self.agent} / {self.tool} / {self.state}"
