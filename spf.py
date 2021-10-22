import dns.resolver
import argparse
import sys
import tldextract
from xml.etree.ElementTree import *
from time import gmtime, strftime
import re
import socket

version = "1.2"

no_dmarc = "ID1"
no_spf = "ID2"
full_review = "ID3"
weak_dmarc = "ID4"
weak_spf = "ID5"

ET = ElementTree()
items_xml = Element('items')
items_xml.set('version',version)
items_xml.set('source','SureFormat')

current_time = strftime("dmc-result_%H-%M-%S_%d-%m-%Y", gmtime())

parser = argparse.ArgumentParser(description='SPF and DMARC Analyser')
parser.add_argument('--domain','-d',help='Enter the Domain name to veriify. E.g. ins1gn1a.com',required=True,nargs='+')
parser.add_argument('-oX','--xml',required=False,help='Specify the filename to save the XML output (e.g. -oX 123456) or the file will default to the start-time.',default=current_time,dest='xml_job_name')
args = parser.parse_args()

spf_record = False
dmarc_record = False

txt_list = []
temp_dmarc = []

def xml_file_write(z):
    with open(args.xml_job_name + ".xml",'w') as xml_file:
        xml_file.write(z)


def vuln_append_print(x):
    print (x)
    return (x + "\n")

for domain in args.domain:

    item_xml = SubElement(items_xml, "item", {'ipaddress':socket.gethostbyname(domain), 'hostname':domain})
    services_xml = SubElement(item_xml,"services")
    service_xml = SubElement(services_xml, "service", {'protocol':'tcp', 'port':'', 'name':''})
    vulnerabilities_xml = SubElement(service_xml, 'vulnerabilities')

    vulnerabilities_array = []
    vuln_review = ""

    dmarc_tld_check = ""

    print ("\n")

    try:
        # SPF and Other Checks
        for txt in dns.resolver.query(domain,'TXT').response.answer:
            txt_list.append(txt.to_text())
    except:
        extracted = tldextract.extract(domain)
        tld = "{}.{}".format(extracted.domain, extracted.suffix)

        try:
            for txt in dns.resolver.query(tld,'TXT').response.answer:
                txt_list.append(txt.to_text())
        except:
            sys.exit("[!] No TXT records exist for " + domain)

    txt_list = txt_list[0].split('\n')

    # DMARC Checks
    try:
        try:
            for txt in dns.resolver.query(("_dmarc." + domain),'TXT').response.answer:
                temp_dmarc.append(txt.to_text())
            if len(temp_dmarc[0]) > 1:
                txt_list.append(temp_dmarc[0])
            dmarc_domain = domain


        except:
            extracted = tldextract.extract(domain)
            dmarc_domain = "{}.{}".format(extracted.domain, extracted.suffix)
            dmarc_tld_check = "DMARC checks were performed against '" + dmarc_domain + "' as '" + domain + "' contained no TXT records and/or did not exist."
            for txt in dns.resolver.query(("_dmarc." + dmarc_domain),'TXT').response.answer:
                temp_dmarc.append(txt.to_text())
            if len(temp_dmarc[0]) > 1:
                txt_list.append(temp_dmarc[0])

    except:
        vuln_review = vuln_review + vuln_append_print("[!] No DMARC Policy Set Within '_dmarc." + dmarc_domain + "'")
        vulnerabilities_array.append([no_dmarc, "There were no DMARC records found within the TXT entries for '_dmarc." + dmarc_domain + "'. Implementing DMARC alongside SPF would provide granular control for the management and monitoring of email spoofing. " + dmarc_tld_check])


    for x in txt_list:
        if "v=spf" in x.lower():
            spf_record = x
        if "v=DMARC" in x:
            dmarc_record = x

    # Main
    vuln_review = vuln_review + vuln_append_print("[*] Domain: " + domain)

    # SPF Checking

    # Identify servers/hosts in SPF record 
    allowed_servers = []
    spf_allowed_count = 0
    spf_txt = spf_record
    try:
        # contatenate long entries (TXT records are max 255 chars)
        spf_txt = spf_txt[ spf_txt.find( "TXT " ) +4: ]
        if len(spf_txt) > 257:
            spf_txt = re.sub( '"\s+"', "", spf_txt )
        for item in (spf_txt.split(" ")):
            if "include:" in item or "ip4:" in item or "ip6:" in item or "mx:" in item or "a:" in item or "ptr:" in item:
                spf_allowed_count += 1
                allowed_servers.append(item.split(":")[1])
            if item == "mx":
                spf_allowed_count += 1
                allowed_servers.append( "MX-servers" )
    except:
        vuln_review = vuln_review + vuln_append_print("[!] Unable to analyse SPF record  for '" + domain + "'.")

    # Process checks against *all
    if spf_record:
        vuln_review = vuln_review + vuln_append_print("    [+] SPF: " + spf_txt )
        if "-all" in spf_record:
            vuln_review = vuln_review + vuln_append_print("\t[+] Only the following mail servers are authorised to send mail from the " + domain + " domain:")
            for z in allowed_servers:
                vuln_review = vuln_review + vuln_append_print("\t    - " + z.split(" ")[0])
        elif "~all" in spf_record:
            vuln_review = vuln_review + vuln_append_print("\t[+] Only the following mail servers are authorised to send mail from the " + domain + " domain with a soft-fail for non-authorised servers, however '~all' should only be used as a transition to '-all':")
            for z in allowed_servers:
                vuln_review = vuln_review + vuln_append_print("\t    - " + z.split(" ")[0])
        else:
            vuln_review = vuln_review + vuln_append_print("\t[!] The " + domain + " domain is configured in a way that would allow domain email spoofing to be performed.")
            spf_spoofing = "The domain " + domain + " was found to not have a secure SPF record configured, and as such it would be possible to spoof emails from the organisation (e.g. user.name@" + domain + "). The SPF record was set as the following:\n"
            spf_spoofing = spf_spoofing + "- " + str(spf_record.rstrip())
            vulnerabilities_array.append([weak_spf, spf_spoofing])
        if "redirect:" in spf_record:
            vuln_review = vuln_review + vuln_append_print("\t[!] The redirect modifier is configured within the SPF record.")
    else:
        vuln_review = vuln_review + vuln_append_print("\t[!] The " + domain + " domain does not utilise SPF records for authorising mail servers and is vulnerable to domain email spoofing.")
        vulnerabilities_array.append([no_spf, "There were no SPF (Sender Policy Framework) entries found within the TXT records for '" + domain + "'. The domain '" + domain + "' was therefore vulnerable to domain email spoofing."])

    if dmarc_record:
        vuln_review = vuln_review + vuln_append_print("    [+] DMARC: " + dmarc_record.split("TXT ")[1])
        dmarc_policy_reject = False
        dmarc_params = dmarc_record.split(";")
        for p in dmarc_params:
            # Policy checks: reject, none, quarantine
            if " p=quarantine" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[+] p=quarantine: Suspicious emails will be marked as suspected SPAM.")
            elif " p=reject" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[+] p=reject: Emails that fail DKIM or SPF checks will be rejected. (Strong)")
                dmarc_policy_reject = True
            elif " p=none" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[-] p=none: No actions will be performed against emails that have failed DMARC checks. (Weak)")

            # Sender-name (domain/subdomain checks)
            if "adkim=r" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[-] adkim=r (Relaxed Mode): Emails from *." + domain + " are permitted.")
            elif "adkim=s" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[+] adkim=s (Strict Mode): Sender domains must match DKIM mail headers exactly. E.g. if 'd=" + domain + "' then emails are not permitted from subdomains. (Strong)")

            # Percentage Check 
            if "pct=" in p.lower():
                percent_val = p.split("=")[1]
                vuln_review = vuln_review + vuln_append_print("\t[_] pct=" + percent_val + ": " + percent_val + "% of received mail is subject to DMARC processing")

            if "aspf=r" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[-] aspf=r (Relaxed Mode): Any sub-domain from " + domain + " are permitted to match DMARC to SPF records.")
            elif "aspf=s" in p.lower():
                vuln_review = vuln_review + vuln_append_print("\t[+] aspf=s (Strict Mode): The 'header from' domain and SPF must match exactly to pass DMARC checks.")

            # Check for SPF/DMARC non-authorsed rejection (No mail)
            if "aspf=s" in p.lower() and spf_allowed_count == 0 and dmarc_policy_reject:
                vuln_review = vuln_review + vuln_append_print("\t[!] aspf=s: No email can be sent from the " + domain + " domain. No mail servers authorised in SPF and DMARC rejection enabled.")
        
            if "rua=" in p.lower():
                if "mailto:" not in p.lower():
                    vuln_review = vuln_review + vuln_append_print("\t[!] rua=: Aggregate mail reports will not be sent as incorrect syntax is used. Prepend 'mailto:' before mail addresses.")
                else:
                    if "," in p:
                        vuln_review = vuln_review + vuln_append_print("\t[+] rua=: Aggregate mail reports will be sent to the following email addresses:")
                        dmarc_mail_list = p.split(",")
                        for dmarc_rua in dmarc_mail_list:
                            try:
                                dmarc_rua = dmarc_rua.split(":")[1]
                            except:
                                dmarc_rua = dmarc_rua
                            vuln_review = vuln_review + vuln_append_print("\t    - " + dmarc_rua)
                    else:
                        vuln_review = vuln_review + vuln_append_print("\t[+] rua=" + p[5:] + ": Aggregate mail reports will be sent to this address.")

            if "ruf=" in p.lower():
                if "mailto:" not in p.lower():
                    vuln_review = vuln_review + vuln_append_print("\t[!] ruf=: Mail failure reports will not be sent as incorrect syntax is used. Prepend 'mailto:' before mail addresses.")
                else:
                    if "," in p:
                        vuln_review = vuln_review + vuln_append_print("\t[+] ruf=: Mail failure reports will be sent to the following email addresses:")
                        dmarc_mail_list = p.split(",")
                        for dmarc_ruf in dmarc_mail_list:
                            try:
                                dmarc_ruf = dmarc_ruf.split(":")[1]
                            except:
                                dmarc_ruf = dmarc_ruf
                            vuln_review = vuln_review + vuln_append_print("\t    - " + dmarc_ruf)
                    else:
                        vuln_review = vuln_review + vuln_append_print("\t[+] ruf=" + p[5:] + ": Failure reports sent to this address.")


    for vulnerability_data in vulnerabilities_array:
        vuln_id,vuln_info = vulnerability_data
        vuln_xml = SubElement(vulnerabilities_xml,"vulnerability",{'id':vuln_id})
        vuln_info_xml = SubElement(vuln_xml,"information").text = vuln_info

    if len(vuln_review) > 0:
        vuln_xml_review = SubElement(vulnerabilities_xml, "vulnerability", {'id': full_review})
        vuln_review_info_xml = SubElement(vuln_xml_review, "information").text = vuln_review

    xml_file_write((tostring(items_xml, encoding='utf8', method='xml').decode('utf-8')))