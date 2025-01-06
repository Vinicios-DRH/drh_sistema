function success(pos) {
    document.getElementById('latitude').value = pos.coords.latitude;
    document.getElementById('longitude').value = pos.coords.longitude;
}

navigator.geolocation.getCurrentPosition(success);