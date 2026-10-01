// cv-content.typ — THE SOURCE OF TRUTH for every adapter in adapters/.
// Only real data goes here: every fact is rendered into every template.
#let cv = (
  author: "Simi Dalo Mwadkwon",
  profession: "Senior Data Scientist · Machine Learning Engineer",
  location: "Bonn, Germany",
  email: "simi.mwadkwon@email.ng",
  phone: "+49 170 000 0000",
  social: (("https://example.com/simi", "example.com/simi"),),
  contact: [simi.mwadkwon\@email.ng #h(0.6em) | #h(0.6em) +49 170 000 0000],
  // ridgeline's narrow rail takes the contact block as separate items
  contact-items: (
    [simi.mwadkwon\@email.ng],
    [+49 170 000 0000],
    [Bonn, Germany],
    [#link("https://example.com/simi")[example.com/simi]],
  ),
  doc-title: "Curriculum Vitae",    // the document label — blank it to drop it everywhere
  tagline: none,                    // or [...] e.g. "Application: Senior Data Scientist, Rankings"
  meta: none,                       // or [...] e.g. date of birth, nationality
  // style: (                       // optional — omit to keep the template exactly as designed
  //   accent: "#33475a",           // accent colour
  //   font: "Libertinus Serif",    // font family
  //   size: "11pt",                // base font size
  //   margin: "2cm",               // page margin
  //   hyphenate: false,            // hyphenation (off is safer for ATS parsing)
  //   heading: "profession",       // which heading variant this build uses, one of:
  //                                //   "profession"          name + headline (template default)
  //                                //   "none"                name only
  //                                //   "cv-label"            name + document label
  //                                //   "profession+cv-label" headline then label
  //                                //   "tagline"             name + tagline (per application)
  // ),
  sections: (
    (
      title: "Profile",
      prose: [Two sentences that say what you do and the number that proves it.],
    ),
    (
      title: "Experience",
      entries: (
        (
          title: "Senior Data Scientist",
          subtitle: "Example GmbH",
          dates: "2023 – Present",
          location: "Bonn, Germany",
          bullets: (
            "Shipped a ranking model that moved conversion 12% in six weeks.",
            "Cut training cost threefold by fine-tuning instead of training from scratch.",
          ),
        ),
        (
          // secondary rows that are not bullets go in `lines` — a degree list, a certificate
          // line, a skills run — so no row of an entry can go missing
          title: "MSc Financial Engineering",
          subtitle: "Example University",
          dates: "2018 – 2021",
          lines: ("BEng Electrical Engineering — Example Institute, Jos, Nigeria, 1995 – 2000",),
        ),
      ),
    ),
  ),
)
