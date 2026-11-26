from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from core.mixins import ModuleRequiredMixin, ProprietaireEvenementMixin
from core.permissions import evenements_geres
from evenements.models import Evenement

from .forms import SeanceForm
from .models import Seance


def _ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _seance_payload(seance):
    from django.utils import timezone as django_timezone

    local_date = django_timezone.localtime(seance.date)
    return {
        "id": seance.pk,
        "titre": seance.titre,
        "description": seance.description,
        "date": local_date.strftime("%Y-%m-%dT%H:%M"),
        "date_label": local_date.strftime("%d/%m/%Y · %H:%M"),
        "detail_date": local_date.strftime("%A %d %B %Y à %H:%M"),
    }


class ProgrammesAccueilView(ModuleRequiredMixin, ListView):
    """Page d'entrée du module Programmes : accès direct aux séances de tous les événements gérés."""
    module = "programmes"
    template_name = "programmes/index.html"
    context_object_name = "evenements"
    paginate_by = 12

    def get_queryset(self):
        qs = evenements_geres(self.request.user).annotate(nb_seances=Count("seances")).order_by("-date_debut")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(titre__icontains=q) | Q(seances__titre__icontains=q)).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["prochaines_seances"] = (Seance.objects.filter(evenement__in=evenements_geres(self.request.user),
                                                           date__gte=timezone.now())
                                     .select_related("evenement").order_by("date")[:8])
        return ctx


class SeanceCreateView(ProprietaireEvenementMixin, CreateView):
    model = Seance
    form_class = SeanceForm

    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.evenement = self.get_evenement()
        return form

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.get_evenement(), **kwargs)

    def get_success_url(self):
        messages.success(self.request, "Séance ajoutée au programme.")
        return self.object.evenement.get_absolute_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        if _ajax(self.request):
            return JsonResponse({"seance": _seance_payload(self.object)}, status=201)
        return response

    def form_invalid(self, form):
        if _ajax(self.request):
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        return super().form_invalid(form)


class SeanceUpdateView(ProprietaireEvenementMixin, UpdateView):
    model = Seance
    form_class = SeanceForm

    def get_evenement(self):
        return self.get_object().evenement

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.object.evenement, **kwargs)

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        if _ajax(self.request):
            return JsonResponse({"seance": _seance_payload(self.object)})
        return response

    def form_invalid(self, form):
        if _ajax(self.request):
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        return super().form_invalid(form)


class SeanceDeleteView(ProprietaireEvenementMixin, DeleteView):
    model = Seance

    def get_evenement(self):
        return self.get_object().evenement

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        evenement = self.object.evenement
        if _ajax(request):
            self.object.delete()
            return JsonResponse({"deleted": True, "id": kwargs["pk"], "evenement": evenement.pk})
        return super().post(request, *args, **kwargs)


class ProgrammesPdfView(TemplateView):
    """Exporte un programme pour toute personne autorisée à consulter l'événement."""

    def get_evenement(self):
        evenement = get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])
        user = self.request.user
        if evenement.statut != Evenement.Statut.BROUILLON:
            return evenement
        if user.is_authenticated and (user.est_admin or evenement.organisateur_id == user.pk):
            return evenement
        from django.http import Http404
        raise Http404

    def get(self, request, *args, **kwargs):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg
            from fontTools.ttLib import TTFont as FontToolsTTFont
            from fontTools.varLib.instancer import instantiateVariableFont
        except ImportError:
            return HttpResponse("ReportLab, svglib et fontTools sont requis pour exporter le programme.", status=503)

        evenement = self.get_evenement()
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="programme-{evenement.pk}.pdf"'
        from django.contrib.staticfiles import finders
        from django.utils import timezone as django_timezone
        from html import escape
        from pathlib import Path
        from tempfile import TemporaryDirectory

        primary = colors.HexColor("#512D3B")
        accent = colors.HexColor("#D0A06D")
        muted = colors.HexColor("#796D72")
        border = colors.HexColor("#E9E0D9")
        logo_path = finders.find("img/logo.svg")
        inter_path = finders.find("fonts/Inter.woff2")
        cormorant_path = finders.find("fonts/CormorantGaramond.woff2")
        if not all((logo_path, inter_path, cormorant_path)):
            return HttpResponse("Le logo ou les polices EVENZA sont introuvables dans les fichiers statiques.", status=503)
        logo = svg2rlg(logo_path)
        if logo is None:
            return HttpResponse("Le logo EVENZA ne peut pas être chargé.", status=503)

        with TemporaryDirectory(prefix="evenza-pdf-") as font_dir:
            font_dir = Path(font_dir)

            def register_project_font(source, family, weight):
                font = FontToolsTTFont(source)
                if "fvar" in font:
                    instantiateVariableFont(font, {"wght": weight}, inplace=True)
                font.flavor = None
                ttf_path = font_dir / f"{family}-{weight}.ttf"
                font.save(ttf_path)
                font.close()
                font_name = f"{family}-{weight}"
                pdfmetrics.registerFont(TTFont(font_name, str(ttf_path)))
                return font_name

            inter = register_project_font(inter_path, "EvenzaInter", 400)
            inter_bold = register_project_font(inter_path, "EvenzaInter", 600)
            display = register_project_font(cormorant_path, "EvenzaCormorant", 600)
            pdfmetrics.registerFontFamily(inter, normal=inter, bold=inter_bold, italic=inter, boldItalic=inter_bold)

            body = ParagraphStyle("EvenzaBody", fontName=inter, fontSize=10, leading=15, textColor=colors.HexColor("#342630"), spaceAfter=2 * mm)
            label = ParagraphStyle("EvenzaLabel", parent=body, fontName=inter_bold, textColor=primary, spaceAfter=0)
            event_title = ParagraphStyle("EvenzaEventTitle", fontName=display, fontSize=26, leading=30, textColor=primary, spaceAfter=4 * mm)
            section_title = ParagraphStyle("EvenzaSectionTitle", fontName=inter_bold, fontSize=15, leading=20, textColor=primary, spaceBefore=5 * mm, spaceAfter=3 * mm)
            session_title = ParagraphStyle("EvenzaSessionTitle", fontName=inter_bold, fontSize=11, leading=15, textColor=primary, spaceBefore=3 * mm, spaceAfter=1 * mm, keepWithNext=True)
            session_date = ParagraphStyle("EvenzaSessionDate", parent=body, fontName=inter, textColor=muted, spaceAfter=1 * mm, keepWithNext=True)
            story = [
                Paragraph(escape(evenement.titre), event_title),
                Paragraph(f"<b>Date de début :</b> {django_timezone.localtime(evenement.date_debut):%d/%m/%Y à %H:%M}", body),
                Paragraph(f"<b>Date de fin :</b> {django_timezone.localtime(evenement.date_fin):%d/%m/%Y à %H:%M}", body),
            ]
            if evenement.lieu:
                story.insert(1, Paragraph(f"<b>Lieu :</b> {escape(str(evenement.lieu))}", body))
            story.extend([
                Spacer(1, 4 * mm),
                HRFlowable(width="100%", thickness=1, color=accent, spaceBefore=1 * mm, spaceAfter=2 * mm),
                Paragraph("Au programme :", section_title),
            ])
            for seance in evenement.seances.order_by("date"):
                story.append(Paragraph(escape(seance.titre), session_title))
                story.append(Paragraph(f"<b>Date :</b> {django_timezone.localtime(seance.date):%d/%m/%Y à %H:%M}", session_date))
                description = (seance.description or "").strip()
                if description:
                    safe_description = "<br/>".join(escape(line) for line in description.splitlines())
                    story.append(Paragraph(f"<b>Description :</b> {safe_description}", body))
                story.append(HRFlowable(width="100%", thickness=0.4, color=border, spaceBefore=1 * mm, spaceAfter=1 * mm))

            doc = SimpleDocTemplate(
                response, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
                topMargin=32 * mm, bottomMargin=20 * mm, title=f"Programme - {evenement.titre}",
            )

            def draw_page(canvas, document):
                self._header(canvas, document, logo, renderPDF, inter_bold, primary, accent, mm)
                self._footer(canvas, document)

            doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
        return response

    @staticmethod
    def _header(canvas, doc, logo, render_pdf, font_name, primary, accent, mm):
        from reportlab.lib.pagesizes import A4

        canvas.saveState()
        logo_height = 11 * mm
        scale = logo_height / logo.height
        x, y = 20 * mm, A4[1] - 23 * mm
        canvas.saveState()
        canvas.translate(x, y)
        canvas.scale(scale, scale)
        render_pdf.draw(logo, canvas, 0, 0)
        canvas.restoreState()
        canvas.setFont(font_name, 13)
        canvas.setFillColor(primary)
        canvas.drawString(x + logo_height + 3 * mm, y + 3.2 * mm, "EVENZA")
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(0.8)
        canvas.line(20 * mm, y - 4 * mm, A4[0] - 20 * mm, y - 4 * mm)
        canvas.restoreState()

    @staticmethod
    def _footer(canvas, doc):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColorRGB(0.32, 0.18, 0.23)
        canvas.drawString(18 * mm, 10 * mm, "EVENZA")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
