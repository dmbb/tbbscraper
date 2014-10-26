CREATE TABLE features (
	locale TEXT NOT NULL CHECK (locale <> ''),
	url INTEGER NOT NULL REFERENCES url_strings(id),
	tfidf TEXT,
	tfidf_row TEXT,
	tfidf_column TEXT,
	code TEXT,
	detail TEXT,
	isRedir INTEGER,
	redirDomain TEXT,
	html_length INTEGER,
	content_length INTEGER,
	dom_depth INTEGER,
	number_of_tags INTEGER,
	unique_tags INTEGER,
	PRIMARY KEY(locale, url)
);
