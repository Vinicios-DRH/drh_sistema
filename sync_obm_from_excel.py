from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func
from werkzeug.utils import secure_filename
import plotly.graph_objects as go
import plotly.io as pio











@app.route('/viaturas/nova', methods=['GET', 'POST'])
@login_required
def cadastrar_viatura():
    form = FormViatura()

    form.obm_id.choices = [('', '-- Selecione a OBM --')] + [
        (str(obm.id), obm.sigla) for obm in Obm.query.order_by(Obm.sigla.asc()).all()
    ]

    if form.validate_on_submit():
        prefixo = (form.prefixo.data or '').strip().upper()
        placa = (form.placa.data or '').strip().upper()
        marca_modelo = (form.marca_modelo.data or '').strip()
        obm_id = form.obm_id.data

        viatura_existente_prefixo = Viaturas.query.filter_by(prefixo=prefixo).first()
        if viatura_existente_prefixo:
            flash('Já existe uma viatura cadastrada com esse prefixo.', 'warning')
            return render_template('viaturas/cadastrar_viatura.html', form=form)

        if placa:
            viatura_existente_placa = Viaturas.query.filter_by(placa=placa).first()
            if viatura_existente_placa:
                flash('Já existe uma viatura cadastrada com essa placa.', 'warning')
                return render_template('viaturas/cadastrar_viatura.html', form=form)

        nova_viatura = Viaturas(
            prefixo=prefixo,
            placa=placa,
            marca_modelo=marca_modelo,
            obm_id=int(obm_id) if obm_id else None
        )

        database.session.add(nova_viatura)
        database.session.commit()

        flash('Viatura cadastrada com sucesso.', 'success')
        return redirect(url_for('listar_viaturas'))

    return render_template('viaturas/cadastrar_viatura.html', form=form)


@app.route("/viaturas", methods=["GET"])
def escolher_obm():
    obms = Obm.query.order_by(Obm.sigla.asc()).all()
    return render_template("viaturas_escolher_obm.html", obms=obms)