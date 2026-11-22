from io import BytesIO
from datetime import datetime, time
from xml.sax.saxutils import escape

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from core.mixins import ProprietaireEvenementMixin
from evenements.models import Evenement

from .forms import SeanceForm
from .models import Seance


def _seance_payload(seance):
    return {
        "id": seance.pk,
        "titre": seance.titre,
        "description": seance.description,
        "date": seance.date.isoformat(),
        "date_affichee": seance.date.strftime("%d/%m/%Y à %H:%M"),
    }


def _visible_event(request, pk):
    queryset = Evenement.objects.select_related("lieu", "categorie", "organisateur")
    user = request.user
    if user.is_authenticated and user.est_admin:
        return get_object_or_404(queryset, pk=pk)
    if user.is_authenticated:
        return get_object_or_404(
            queryset.filter(statut__in=[Evenement.Statut.PUBLIE, Evenement.Statut.ANNULE])
            | queryset.filter(organisateur=user),
            pk=pk,
        )
    return get_object_or_404(queryset, pk=pk, statut=Evenement.Statut.PUBLIE)


def _filtered_seances(event, params):
    raw_start_date = params.get("from_date", params.get("from", ""))
    raw_start_time = params.get("from_time", "")
    raw_end_date = params.get("to_date", params.get("to", ""))
    raw_end_time = params.get("to_time", "")
    start_date = parse_date(raw_start_date) if raw_start_date else None
    end_date = parse_date(raw_end_date) if raw_end_date else None
    start_time = parse_time(raw_start_time) if raw_start_time else time.min
    end_time = parse_time(raw_end_time) if raw_end_time else time.max
    if (raw_start_date and start_date is None) or (raw_end_date and end_date is None):
        raise ValueError("Les dates du filtre sont invalides.")
    if (raw_start_time and start_time is None) or (raw_end_time and end_time is None):
        raise ValueError("Les heures du filtre sont invalides.")
    start = timezone.make_aware(datetime.combine(start_date, start_time)) if start_date else None
    end = timezone.make_aware(datetime.combine(end_date, end_time)) if end_date else None
    if start and end and start > end:
        raise ValueError("Le début du filtre doit précéder sa fin.")
    queryset = event.seances.order_by("date")
    if start:
        queryset = queryset.filter(date__gte=start)
    if end:
        queryset = queryset.filter(date__lte=end)
    return queryset, start, end


def _programme_pdf_response(event, seances, start=None, end=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # Palette issue du design system Evenza : bordeaux, champagne et ivoire.
    primary = colors.HexColor("#512D3B")
    dark = colors.HexColor("#292128")
    accent = colors.HexColor("#D0A06D")
    cream = colors.HexColor("#F7F3EB")
    surface = colors.HexColor("#FFFDFC")
    muted = colors.HexColor("#796D72")
    border = colors.HexColor("#E9E0D9")
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Programme - {event.titre}",
        author="EVENZA",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("PdfBrand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=colors.white, tracking=1.8))
    styles.add(ParagraphStyle("PdfBrandMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#F7F3EB"), alignment=TA_RIGHT))
    styles.add(ParagraphStyle("PdfTitle", parent=styles["Title"], fontName="Times-Bold", fontSize=25, leading=29, textColor=primary, spaceAfter=5))
    styles.add(ParagraphStyle("PdfEvent", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=dark, spaceAfter=10))
    styles.add(ParagraphStyle("PdfLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=muted, uppercase=True, tracking=0.8))
    styles.add(ParagraphStyle("PdfInfo", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=dark))
    styles.add(ParagraphStyle("PdfFilter", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=8.5, leading=12, textColor=muted))
    styles.add(ParagraphStyle("PdfSessionTime", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=accent))
    styles.add(ParagraphStyle("PdfSessionTitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=primary))
    styles.add(ParagraphStyle("PdfSessionDescription", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=13, textColor=muted, spaceBefore=4))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(border)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(18 * mm, 8 * mm, "EVENZA")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    story = []
    brand = Table([[Paragraph("EVENZA", styles["PdfBrand"]), Paragraph("PROGRAMME ÉVÉNEMENTIEL", styles["PdfBrandMeta"])]], colWidths=[95 * mm, 79 * mm])
    brand.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.extend([brand, Spacer(1, 13 * mm), Paragraph("Programme de l'événement", styles["PdfTitle"]), Paragraph(escape(event.titre), styles["PdfEvent"])])

    info = [
        [Paragraph("DATES", styles["PdfLabel"]), Paragraph("LIEU", styles["PdfLabel"]), Paragraph("CATÉGORIE", styles["PdfLabel"])],
        [Paragraph(f"Du {event.date_debut:%d/%m/%Y à %H:%M}<br/>Au {event.date_fin:%d/%m/%Y à %H:%M}", styles["PdfInfo"]), Paragraph(f"{escape(event.lieu.nom)}<br/>{escape(event.lieu.adresse)}, {escape(event.lieu.ville)}", styles["PdfInfo"]), Paragraph(f"{escape(event.categorie.nom)}<br/>{event.capacite} places · {event.prix:.2f} €", styles["PdfInfo"])],
    ]
    info_table = Table(info, colWidths=[58 * mm, 65 * mm, 51 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cream), ("BOX", (0, 0), (-1, -1), 0.6, border),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, border), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    if start or end:
        story.extend([Spacer(1, 5 * mm), Paragraph(f"Filtre appliqué : {start.strftime('%d/%m/%Y %H:%M') if start else 'début'} → {end.strftime('%d/%m/%Y %H:%M') if end else 'fin'}", styles["PdfFilter"])])
    story.extend([Spacer(1, 11 * mm), Paragraph("Déroulé des séances", styles["PdfEvent"])])

    sessions = list(seances)
    if not sessions:
        story.append(Paragraph("Aucune séance pour cet intervalle.", styles["PdfFilter"]))
    for seance in sessions:
        content = [Paragraph(seance.date.strftime("%d/%m/%Y · %H:%M"), styles["PdfSessionTime"]), Paragraph(escape(seance.titre), styles["PdfSessionTitle"])]
        if seance.description:
            content.append(Paragraph(escape(seance.description), styles["PdfSessionDescription"]))
        session = Table([[content]], colWidths=[174 * mm])
        session.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), surface), ("BOX", (0, 0), (-1, -1), 0.5, border),
            ("LINEBEFORE", (0, 0), (0, 0), 3, accent), ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        story.extend([KeepTogether(session), Spacer(1, 4 * mm)])

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="programme-{event.pk}.pdf"'
    return response


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
        messages.success(self.request, "Séance ajoutée à l'événement.")
        return self.object.evenement.get_absolute_url()


class SeanceUpdateView(ProprietaireEvenementMixin, UpdateView):
    model = Seance
    form_class = SeanceForm

    def get_evenement(self):
        return self.get_object().evenement

    def get_context_data(self, **kwargs):
        return super().get_context_data(evenement=self.object.evenement, **kwargs)

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()


class SeanceDeleteView(ProprietaireEvenementMixin, DeleteView):
    model = Seance

    def get_evenement(self):
        return self.get_object().evenement

    def get_success_url(self):
        return self.object.evenement.get_absolute_url()


class SeanceCreateApiView(ProprietaireEvenementMixin, View):
    def get_evenement(self):
        return get_object_or_404(Evenement, pk=self.kwargs["evenement_pk"])

    def post(self, request, evenement_pk):
        event = self.get_evenement()
        form = SeanceForm(request.POST)
        form.instance.evenement = event
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        seance = form.save()
        return JsonResponse({"seance": _seance_payload(seance), "message": "Séance ajoutée."}, status=201)


class SeanceUpdateApiView(ProprietaireEvenementMixin, View):
    def get_object(self):
        return get_object_or_404(Seance.objects.select_related("evenement"), pk=self.kwargs["pk"])

    def get_evenement(self):
        return self.get_object().evenement

    def post(self, request, pk):
        seance = self.get_object()
        form = SeanceForm(request.POST, instance=seance)
        form.instance.evenement = seance.evenement
        if not form.is_valid():
            return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
        seance = form.save()
        return JsonResponse({"seance": _seance_payload(seance), "message": "Séance modifiée."})


class SeanceDeleteApiView(ProprietaireEvenementMixin, View):
    def get_object(self):
        return get_object_or_404(Seance.objects.select_related("evenement"), pk=self.kwargs["pk"])

    def get_evenement(self):
        return self.get_object().evenement

    def post(self, request, pk):
        seance = self.get_object()
        titre = seance.titre
        seance.delete()
        return JsonResponse({"message": f"La séance « {titre} » a été supprimée."})


class ProgrammePdfView(View):
    def get(self, request, evenement_pk):
        event = _visible_event(request, evenement_pk)
        try:
            seances, start, end = _filtered_seances(event, request.GET)
        except ValueError as error:
            return HttpResponseBadRequest(str(error))

        return _programme_pdf_response(event, seances, start, end)

        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas

        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
        buffer = BytesIO()
        document = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        primary = HexColor("#512D3B")
        accent = HexColor("#D0A06D")
        font = "HeiseiMin-W3"
        y = height - 58

        def heading(text, size=18):
            nonlocal y
            document.setFillColor(primary)
            document.setFont(font, size)
            document.drawString(48, y, text)
            y -= size + 12

        def line(text, size=10, color=HexColor("#292128")):
            nonlocal y
            if y < 60:
                document.showPage()
                y = height - 58
            document.setFillColor(color)
            document.setFont(font, size)
            document.drawString(52, y, text[:110])
            y -= size + 7

        heading("PROGRAMME")
        line(event.titre, 22, primary)
        line(f"{event.lieu.nom} · {event.lieu.ville}", 11)
        line(
            f"Du {event.date_debut:%d/%m/%Y %H:%M} au {event.date_fin:%d/%m/%Y %H:%M}",
            10,
        )
        if start or end:
            line(
                f"Filtre : {start.strftime('%d/%m/%Y') if start else 'début'} → "
                f"{end.strftime('%d/%m/%Y') if end else 'fin'}",
                9,
                HexColor("#806B73"),
            )
        y -= 10
        document.setStrokeColor(accent)
        document.line(48, y, width - 48, y)
        y -= 24

        sessions = list(seances)
        if not sessions:
            line("Aucune séance pour cet intervalle.", 11, HexColor("#806B73"))
        for seance in sessions:
            document.setFillColor(accent)
            document.circle(58, y + 3, 4, fill=1, stroke=0)
            line(seance.date.strftime("%d/%m/%Y · %H:%M"), 10, primary)
            line(seance.titre, 14, primary)
            if seance.description:
                line(seance.description, 10, HexColor("#806B73"))
            y -= 8

        document.save()
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="programme-{event.pk}.pdf"'
        return response
