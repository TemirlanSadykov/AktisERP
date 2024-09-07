
  document.addEventListener("DOMContentLoaded", function () {
    // Get the current URL path and split it into segments
    const path = window.location.pathname;
    const segments = path.split("/").filter(Boolean);  // Remove empty segments

    const breadcrumbList = document.getElementById("breadcrumb");

    // Add the "Home" breadcrumb
    // const homeCrumb = document.createElement("li");
    // homeCrumb.classList.add("breadcrumb-item");
    // const homeLink = document.createElement("a");
    // homeLink.href = "/";
    // homeLink.textContent = "Home";
    // homeCrumb.appendChild(homeLink);
    // breadcrumbList.appendChild(homeCrumb);

    // Create breadcrumbs for each segment
    let cumulativePath = "";
    segments.forEach((segment, index) => {
      cumulativePath += `/${segment}`;
      const crumb = document.createElement("li");

      // If it's the last segment, make it active, otherwise make it a link
      if (index === segments.length - 1) {
        crumb.classList.add("breadcrumb-item", "active");
        crumb.textContent = segment.charAt(0).toUpperCase() + segment.slice(1);
        crumb.setAttribute("aria-current", "page");
      } else {
        crumb.classList.add("breadcrumb-item");
        const link = document.createElement("a");
        link.href = cumulativePath;
        link.textContent = segment.charAt(0).toUpperCase() + segment.slice(1);
        crumb.appendChild(link);
      }
      breadcrumbList.appendChild(crumb);
      console.log(breadcrumbList)
    });
  });
