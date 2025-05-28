from bs4 import BeautifulSoup

def parse_scholar_email_html(html_content):
    """
    Parses the HTML content of a Google Scholar alert email to extract articles.
    Returns a list of dictionaries, where each dictionary contains:
    - title: The title of the article.
    - link: The direct link to the article.
    - summary: The snippet/summary provided by Google Scholar.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    articles = []

    # Find all <h3> tags which seem to be the main container for each article entry
    # The title is within an <a> tag with class "gse_alrt_title" inside these <h3> tags.
    h3_tags = soup.find_all("h3")

    for h3_tag in h3_tags:
        title_anchor = h3_tag.find("a", class_="gse_alrt_title")
        
        if title_anchor:
            title = title_anchor.get_text(strip=True)
            link = title_anchor.get("href", "")
            
            # The summary is typically in a <div> with class "gse_alrt_sni"
            # that follows the <h3> tag containing the title.
            # We search for the next sibling div with this class.
            summary_tag = None
            current_sibling = h3_tag.find_next_sibling()
            while current_sibling:
                if current_sibling.name == "div" and "gse_alrt_sni" in current_sibling.get("class", []):
                    summary_tag = current_sibling
                    break
                # Stop if we hit another h3, which would be the next article
                if current_sibling.name == "h3":
                    break
                current_sibling = current_sibling.find_next_sibling()

            summary = ""
            if summary_tag:
                summary = summary_tag.get_text(strip=True)
            
            if title and link: # Summary can be empty
                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary
                })
                
    return articles

if __name__ == "__main__":
    # Example HTML snippet based on the user-provided structure
    sample_html_content = """
    <!doctype html><html xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office"><head><!--[if gte mso 9]><xml><o:OfficeDocumentSettings><o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]--><style>body{background-color:#fff}.gse_alrt_title{text-decoration:none}.gse_alrt_title:hover{text-decoration:underline} @media screen and (max-width: 599px) {.gse_alrt_sni br{display:none;}}</style></head><body><!--[if gte mso 9]><table cellpadding="0" cellspacing="0" border="0"><tr><td style="width:600px"><![endif]--><div style="font-family:arial,sans-serif;font-size:13px;line-height:16px;color:#222;width:100%;max-width:600px">
    <h3 style="font-weight:lighter;font-size:18px;line-height:20px;"></h3><h3 style="font-weight:normal;font-size:18px;line-height:20px;"></h3>
    
    <h3 style="font-weight:normal;margin:0;font-size:17px;line-height:20px;">
        <a href="https://scholar.google.com/scholar_url?url=https://www.sciencedirect.com/science/article/pii/S0021979725012470&amp;hl=zh-CN&amp;sa=X&amp;d=2852679260432743142&amp;ei=c1I1aMqCM_SM6rQP27_9oAg&amp;scisig=AAZF9b_d3RwuVwm-8GXWY5nYW91Z&amp;oi=scholaralrt&amp;hist=Qqxzy1UAAAAJ:15099760743227286020:AAZF9b9hKRPKNrBHf-ooK14R8LHz&amp;html=&amp;pos=0&amp;folt=rel" class="gse_alrt_title" style="font-size:17px;color:#1a0dab;line-height:22px">
        Importance of local coordination microenvironment in regulating CO2 electroreduction catalyzed by Cr-corrole-based single-atom catalysts
        </a>
    </h3>
    <div style="color:#006621;line-height:18px">L Yang, B Li, RY Wang, M Yang, YL Tang, HY Wang… - Journal of Colloid and …, 2025</div>
    <div class="gse_alrt_sni" style="line-height:17px">
        Single-atom catalysts (SACs) with MN 4 active sites are a promising type of <br>electrocatalyst for CO 2 reduction reactions (CO 2 RR). Here, we designed a novel <br>corrole-based CO 2 RR single-atom catalyst Cr-N 4-Cz with a metal center supported …
    </div>
    <div style="width:auto"><table cellpadding="0" cellspacing="0" border="0"><tbody><tr><td><!-- irrelevant content --></td></tr></tbody></table></div><br>

    <h3 style="font-weight:normal;margin:0;font-size:17px;line-height:20px;">
        <a href="https://scholar.google.com/scholar_url?url=https://pubs.acs.org/doi/abs/10.1021/jacs.5c05752&amp;hl=zh-CN&amp;sa=X&amp;d=14672776144934924665&amp;ei=c1I1aMqCM_SM6rQP27_9oAg&amp;scisig=AAZF9b87_1acfWnfPRWVdrjvcSsq&amp;oi=scholaralrt&amp;hist=Qqxzy1UAAAAJ:15099760743227286020:AAZF9b9hKRPKNrBHf-ooK14R8LHz&amp;html=&amp;pos=1&amp;folt=rel" class="gse_alrt_title" style="font-size:17px;color:#1a0dab;line-height:22px">
        Single-Atom Ru-Triggered Lattice Oxygen Redox Mechanism for Enhanced Acidic Water Oxidation
        </a>
    </h3>
    <div style="color:#006621;line-height:18px">M Qi, X Du, X Shi, S Wang, B Lu, J Chen, S Mao… - Journal of the American …, 2025</div>
    <div class="gse_alrt_sni" style="line-height:17px">
        Activating the oxygen anionic redox presents a promising avenue for developing <br>highly active oxygen evolution reaction (OER) electrocatalysts for proton-exchange <br>membrane water electrolyzers (PEMWE). Here, we engineered a lattice-confined Ru …
    </div>
    <div style="width:auto"><table cellpadding="0" cellspacing="0" border="0"><tbody><tr><td><!-- irrelevant content --></td></tr></tbody></table></div><br>

    <h3 style="font-weight:normal;margin:0;font-size:17px;line-height:20px;">
        <span style="font-size:13px;font-weight:normal;color:#1a0dab;vertical-align:2px">[HTML]</span> 
        <a href="https://scholar.google.com/scholar_url?url=https://pubs.acs.org/doi/full/10.1021/acscatal.5c01614&amp;hl=zh-CN&amp;sa=X&amp;d=16729684550490019008&amp;ei=c1I1aMqCM_SM6rQP27_9oAg&amp;scisig=AAZF9b-wFOBq0LUshFA9j1EImcKG&amp;oi=scholaralrt&amp;hist=Qqxzy1UAAAAJ:15099760743227286020:AAZF9b9hKRPKNrBHf-ooK14R8LHz&amp;html=&amp;pos=5&amp;folt=rel" class="gse_alrt_title" style="font-size:17px;color:#1a0dab;line-height:22px">
        Ionomer-Modulated Electrochemical Interface Leading to Improved Selectivity and Stability of Cu2O-Derived Catalysts for CO2 Electroreduction
        </a>
    </h3>
    <div style="color:#006621;line-height:18px">MLJ Peerlings, MET Vink-van Ittersum, JW de Rijk… - ACS Catalysis, 2025</div>
    <div class="gse_alrt_sni" style="line-height:17px">
        Copper is an attractive catalyst for the electrochemical reduction of CO2 to high value <br>C2+ products such as ethylene and ethanol. However, the activity, selectivity and <br>stability of Cu-based catalysts must be improved for industrial applications. In this …
    </div>

    </div></body></html>
    """
    
    parsed_articles = parse_scholar_email_html(sample_html_content)
    if parsed_articles:
        print(f"Found {len(parsed_articles)} articles:")
        for i, article in enumerate(parsed_articles):
            print(f"--- Article {i+1} ---")
            print(f"  Title: {article['title']}")
            print(f"  Link: {article['link']}")
            print(f"  Summary: {article['summary']}")
    else:
        print("No articles found in the sample HTML.")

    # The new parser should handle the structure of sample_html_content_2 as well,
    # as it also uses h3 tags for titles and sibling divs for summaries.
    # Thus, a separate test for sample_html_content_2 with the old logic is no longer needed.
    # print("\n--- Parsing second sample (more realistic) ---")
    # sample_html_content_2 = """
    # <tbody>
    #     <tr>
    #         <td valign="top" style="padding-bottom:10px">
    #         <h3 class="gs_rt" style="margin:0 0 2px;font-size:16px;font-weight:bold">
    #             <a href="https://scholar.google.com/scholar_url?url=LINK_TO_ARTICLE1" class="gse_alrt_title">
    #             A new catalyst for CO2 reduction
    #             </a>
    #         </h3>
    #         <div class="gs_a" style="color:#666;margin-bottom:2px">Author A, Author B - Journal of Stuff, 2024 - publisher.com</div>
    #         <div class="gs_rs" style="color:#666;line-height:1.4em;max-height:5.6em;overflow:hidden">
    #             Herein, we report a novel <b>single-atom</b> <b>catalyst</b> (SAC) for efficient electrochemical 
    #             <b>CO2</b> reduction to CO (<b>CO2RR</b>). The <b>catalyst</b> exhibits high Faradaic efficiency and long-term stability. 
    #             Computational studies using <b>DFT</b> reveal the reaction mechanism.
    #         </div>
    #         </td>
    #     </tr>
    #     <tr>
    #         <td valign="top" style="padding-bottom:10px">
    #         <h3 class="gs_rt" style="margin:0 0 2px;font-size:16px;font-weight:bold">
    #             <a href="https://scholar.google.com/scholar_url?url=LINK_TO_ARTICLE2" class="gse_alrt_title">
    #             Exploring energy storage in modern batteries
    #             </a>
    #         </h3>
    #         <div class="gs_a" style="color:#666;margin-bottom:2px">Scientist C, Scientist D - Energy Reviews, 2024 - journaldomain.org</div>
    #         <div class="gs_rs" style="color:#666;line-height:1.4em;max-height:5.6em;overflow:hidden">
    #             This review covers recent advancements in <b>battery</b> technology, including lithium-ion and solid-state 
    #             batteries. We discuss challenges and future directions for grid-scale energy storage and portable electronics.
    #         </div>
    #         </td>
    #     </tr>
    # </tbody>
    # """
    # parsed_articles_2 = parse_scholar_email_html(sample_html_content_2)
    # if parsed_articles_2:
    #     print(f"Found {len(parsed_articles_2)} articles:")
    #     for i, article in enumerate(parsed_articles_2):
    #         print(f"--- Article {i+1} ---")
    #         print(f"  Title: {article['title']}")
    #         print(f"  Link: {article['link']}")
    #         print(f"  Summary: {article['summary']}")
    # else:
    #     print("No articles found in the second sample HTML.") 