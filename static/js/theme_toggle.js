document.addEventListener('DOMContentLoaded', ()=>{
    const themetoggleButton = document.getElementById("toggle-theme")
    const current_theme = localStorage.getItem("theme") || 'light'

    document.documentElement.className = current_theme

    themetoggleButton.addEventListener('click', ()=>{
     
        fetch('/login/', {
            method: 'POST',
            headers:{
                'X-CSRFToken': 
                document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        }).then( response => response.json()).then(data => {
            document.documentElement.className = data.theme
            localStorage.setItem('theme', data.theme)
           
        }).catch(error => {
            console.error({'Erro ao Alterar o Thema': error})
        })
    })
})