function calculateAge() {
  const birthDate = new Date(document.getElementById('data_nascimento').value);
  const today = new Date();

  birthDate.setUTCHours(0, 0, 0, 0);
  today.setUTCHours(0, 0, 0, 0);

  let age = today.getFullYear() - birthDate.getFullYear();
  const monthDiff = today.getMonth() - birthDate.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
    age--;
  }
  document.getElementById('idade_atual').value = age;
}

function calculateInclusao() {
  const inclusaoDate = new Date(document.getElementById('inclusao').value);
  const today = new Date();

  inclusaoDate.setUTCHours(0, 0, 0, 0);
  today.setUTCHours(0, 0, 0, 0);

  let years = today.getFullYear() - inclusaoDate.getFullYear();
  let months = today.getMonth() - inclusaoDate.getMonth();
  let days = today.getDate() - inclusaoDate.getDate();

  if (days < 0) {
    months--;
    const daysInMonth = new Date(today.getFullYear(), today.getMonth(), 0).getDate();
    days += daysInMonth;
  }

  if (months < 0) {
    years--;
    months += 12;
  }

  const complete25Years = new Date(inclusaoDate.getTime());
  complete25Years.setFullYear(inclusaoDate.getFullYear() + 25);

  const complete30Years = new Date(inclusaoDate.getTime());
  complete30Years.setFullYear(inclusaoDate.getFullYear() + 30);

  complete25Years.setUTCHours(23, 59, 59, 999);
  complete30Years.setUTCHours(23, 59, 59, 999);

  const options = { day: '2-digit', month: '2-digit', year: 'numeric' };
  document.getElementById('completa_25_inclusao').value = complete25Years.toLocaleDateString('pt-BR', options);
  document.getElementById('completa_30_inclusao').value = complete30Years.toLocaleDateString('pt-BR', options);
}

function calculateServiceDetails() {
  const serviceDate = new Date(document.getElementById('efetivo_servico').value);
  const today = new Date();

  serviceDate.setUTCHours(0, 0, 0, 0);
  today.setUTCHours(0, 0, 0, 0);

  let years = today.getFullYear() - serviceDate.getFullYear();
  let months = today.getMonth() - serviceDate.getMonth();
  let days = today.getDate() - serviceDate.getDate();

  if (days < 0) {
    months--;
    const daysInMonth = new Date(today.getFullYear(), today.getMonth(), 0).getDate();
    days += daysInMonth;
  }

  if (months < 0) {
    years--;
    months += 12;
  }

  const totalDays = Math.floor((today - serviceDate) / (1000 * 60 * 60 * 24));

  const complete25Years = new Date(serviceDate.getTime());
  complete25Years.setFullYear(serviceDate.getFullYear() + 25);

  const complete30Years = new Date(serviceDate.getTime());
  complete30Years.setFullYear(serviceDate.getFullYear() + 30);

  complete25Years.setUTCHours(23, 59, 59, 999);
  complete30Years.setUTCHours(23, 59, 59, 999);

  const options = { day: '2-digit', month: '2-digit', year: 'numeric' };
  document.getElementById('completa_25_anos_sv').value = complete25Years.toLocaleDateString('pt-BR', options);
  document.getElementById('completa_30_anos_sv').value = complete30Years.toLocaleDateString('pt-BR', options);

  document.getElementById('anos').value = years;
  document.getElementById('meses').value = months;
  document.getElementById('dias').value = days;
  document.getElementById('total_dias').value = totalDays;
}