
  document.addEventListener("DOMContentLoaded", function () {
    const breadcrumbList = document.getElementById("breadcrumb");

    let cumulativePath = "";
    bread_dict = reteriving_breadcrumb()
    bread_dict.forEach((segment, index) => {
        segment = JSON.parse(segment)
        segment = Object.entries(segment)
        segment.forEach(([key, value]) =>  {
            cumulativePath += `/${value}`;
            const crumb = document.createElement("li");

            if (index === bread_dict.length - 1) {
                crumb.classList.add("breadcrumb-item", "active");
                crumb.textContent = key.charAt(0).toUpperCase() + key.slice(1);
                crumb.setAttribute("aria-current", "page");
            } else {
                crumb.classList.add("breadcrumb-item");
                const link = document.createElement("a");
                link.href = cumulativePath;
                link.addEventListener('click', (event) => {
                    remove_breadcrump(key);
                });
                link.textContent = key.charAt(0).toUpperCase() + key.slice(1);
                crumb.appendChild(link);
            }
            breadcrumbList.appendChild(crumb);
        })        
    })
  });

function remove_breadcrump(item_key){
    let storedTags = localStorage.getItem('bread');
    let tagsArray = storedTags ? JSON.parse(storedTags) : [];

    let keys = Object.keys(tagsArray);
    const index = keys.indexOf(item_key);
    tagsArray = tagsArray.slice(0, index);
    localStorage.setItem('bread', JSON.stringify(tagsArray));
}

function new_breadcrump(item){
    let items = []
    items.push(JSON.stringify(item))
    localStorage.setItem('bread', JSON.stringify(items));

}

function saving_breadcrump(item_key, item){
    let storedTags = localStorage.getItem('bread');
    let tagsArray = storedTags ? JSON.parse(storedTags) : [];
    let newTag = JSON.stringify({[item] :item_key});
    tagsArray.push(newTag)
    localStorage.setItem('bread', JSON.stringify(tagsArray));
}

function reteriving_breadcrumb(){
    let storedTags = localStorage.getItem('bread');
    return storedTags ? JSON.parse(storedTags) : [];
}
