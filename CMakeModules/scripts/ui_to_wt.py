import sys,os,subprocess,re
import xml.dom.minidom
#import html.parser
import HTMLParser
import pprint
import optparse

#Used to convert Qt's ui file to Wt ui class

#defines
layoutWidgets=('Wt::WVBoxLayout', 'Wt::WHBoxLayout', 'Wt::WGridLayout')
nonParentWidgts=('Wt::WVBoxLayout', 'Wt::WHBoxLayout', 'Wt::WGridLayout', 'Wt::WTabWidget')

#utility functions
def camelCase(string):
    string=[char for char in string]
    for i in range(0, len(string)):
        if string[i] in ('_', ' ') and i+1<len(string):
            string[i]=''
            string[i+1]=string[i+1].upper()
    if string:
        string[0]=string[0].lower()
    return ''.join(string)

def find(func, seq):
    for item in seq:
        if func(item):
            return item
    
def rfind(func, seq):
    for item in reversed(seq):
        if func(item):
            return item
    
#MiniDomHelper - shortcuts for the minidom
class MiniDomHelper(object):
    def __init__(self, node):
        assert(node)
        self.node = node
        
    def toString(self):
        if self.node.nodeType == self.node.TEXT_NODE:
            return HTMLParser.HTMLParser().unescape(self.node.toxml().encode('utf-8'))
        return HTMLParser.HTMLParser().unescape(u''.join([node.toxml() for node in self.node.childNodes])).encode('utf-8')
#            return html.parser.HTMLParser().unescape(self.node.toxml().encode('utf-8'))
#        return html.parser.HTMLParser().unescape(u''.join([node.toxml() for node in self.node.childNodes])).encode('utf-8')

    def findAll(self, tag=None, **conditions):
        nodes=[]
        for node in self.node.childNodes:
            if node.nodeType != node.TEXT_NODE:
                if tag and node.tagName != tag:
                    continue
                if 'cl' in conditions:
                    conditions['class'] = conditions['cl']
                    del conditions['cl']
                if not all([node.hasAttribute(key) and node.getAttribute(key) == value for key,value in conditions.iteritems()]):
                    continue
                nodes.append(MiniDomHelper(node))
        return nodes
    
    def find(self, tag=None, **conditions):
        return self.findAll(tag, **conditions)[0]

    def value(self):
        if hasattr(self, 'string'):
            return self.string
        elif hasattr(self, 'bool'):
            return self.bool in ('true', 'True',' ON', '1')
        elif hasattr(self, 'double'):
            return float(self.double)
        elif hasattr(self, 'number'):
            return int(self.number)
        elif hasattr(self, 'set'):
            return self.set.split('|')
        elif hasattr(self, 'enum'):
            return self.enum
        else:
            return self.toString()
#            raise AttributeError
    
    def parent(self):
        parentNode=self.node.parentNode
        if parentNode and not isinstance(parentNode, xml.dom.minidom.Document):
            return MiniDomHelper(parentNode)
        return None

    def tag(self):
        return self.node.tagName
    
    def name(self):
        return self.node.hasAttribute('name') and self.node.getAttribute('name') or None
    
    def cl(self):
        return self.node.hasAttribute('class') and self.node.getAttribute('class') or None
    
    def property(self, propertyName, default=None):
        nodes=self.findAll(tag='property', name=propertyName)
        if nodes:
            return nodes[0].value()
        return default
    
    def hasProperty(self, propertyName):
        nodes=self.findAll(tag='property', name=propertyName)
        if nodes:
            return True
        return False
    
    def attribute(self, attributeName):
        if not self.node.hasAttribute(attributeName):
            raise AttributeError
        return self.node.getAttribute(attributeName)
    
    def isTextNode(self):
        if self.node.nodeType == self.node.TEXT_NODE:
            return True
        else:
            return (len(self.node.childNodes) == 1 and self.node.childNodes[0].nodeType == self.node.TEXT_NODE)
        
    def trace(self):
        localName=self.tag()+'('+','.join(node.value for node in self.node.attributes.values())+')'
        parent=self.parent()
        if parent:
            return parent.trace()+'.'+localName
        return localName
    
    def __getattr__(self, attribute):
        nodes = self.findAll(tag=attribute)
        if not(nodes):
            raise AttributeError
        node = nodes[0]
        if node.isTextNode():
            return node.toString()
        elif len(node.node.childNodes) == 0:
            return ""
        else:
            return node

    def __getitem__(self, key):
        nodes = self.findAll(self, name=key)
        if not(nodes):
            raise KeyError
        return nodes[0]

    def __iter__(self):
        return [MiniDomHelper(node) for node in self.node.childNodes].__iter__()
        

#UIXmlParser - parses .ui xml file        
class UIXmlParser(object):
    def __init__(self, headerFile):
        self.headerFile=headerFile #file handle for the header file to output
        self.wtTypes=list() #list of Wt types used in file
        self.variables=list() #list of variables to define
        self.indent=context['indent']
        self.mainWidgetName=""
        self.mainWidgetClass="" 
        
    def process(self, nodes, context):
        for node in nodes:
            if node.isTextNode():
                continue
            self.processNode(node, context)
            
    def processNode(self, node, context):
        processFunction='process_'+str(node.tag())
        self.tryFunctionCall(processFunction, node, context)
        
    #process functions
    def process_widget(self, node, context):
        try:
            localContext=context.copy()
            self.pushParent(localContext)
            localContext['name']=node.name()
            localContext['variableName']=camelCase(node.name())
            processFunction='process_widget_'+node.attribute('class')
        except AttributeError:
            localContext['variableName']=""
            self.printError("process_widget - %s missing 'class' property"%(node.trace()))
            return
        self.tryFunctionCall(processFunction, node, localContext)
        self.pushChild(context, localContext)

    def process_item(self, node, context):
        if 'className' in context:
            if context['className'] == 'Wt::WComboBox':
                name=node.property('text')
                if name:
                    self.writeHeader("%s->addItem(\"%s\");"%(context['variableName'], name))
                    
    def process_spacer(self, node, context):
#        localContext={}
        localContext=context.copy()
        self.pushParent(localContext)
        localContext['className']='spacer'
        localContext['name']=node.name()
        self.process(node, localContext)
        self.pushChild(context, localContext)
        
    def process_property(self, node, context):
        try:
            name=node.attribute('name')
            processFunction='process_property_'+name
        except AttributeError:
            self.printError("process_property - %s missing 'name' property"%node.trace())
            return
        if not self.tryFunctionCall(processFunction, node, context):
            self.process_property_default(node, context)
        
    def process_attribute(self, node, context):
        try:
            processFunction='process_attribute_'+node.attribute('name')
        except AttributeError:
            self.printError("process_attribute - %s missing 'attribute' property"%node.trace())
            return
        self.tryFunctionCall(processFunction, node, context)

    def process_layout(self, node, context):
        try:
            localContext=context.copy()
            self.pushParent(localContext)
            localContext['variableName']=camelCase(node.name())
            processFunction='process_layout_'+node.attribute('class')
        except AttributeError:
            localContext['variableName']=""
            self.printError("process_layout - %s missing 'class' property"%node.trace())
            return
        self.tryFunctionCall(processFunction, node, localContext)
        self.pushChild(context, localContext)

    def pushParent(self, context):
        if 'variableName' in context:
            context['parentName']=context['variableName']
            context['parentClass']=context['className']
            if 'parentList' not in context:
                context['parentList']=list();
            context['parentList'].append({'variableName':context['variableName'], 'className':context['className']})
        else:
            if 'parentName' in context:
                del context['parentName']
            if 'parentClass' in context:
                del context['parentClass']
        if 'variableName' in context:
            del context['variableName']
        if 'className' in context:
            del context['className']
        
    def pushChild(self, context, childContext):
        if 'parentList' in context:
            context['parentList'].pop()
        if 'className' in childContext:
            if 'children' not in context:
                context['children']=list()
            if 'children' in childContext: #remove children list from child so we do not have a long list of items at the top
                del childContext['children']
            context['children'].append(childContext)
                    
    #process functions for widgets
    def process_widget_QMainWindow(self, node, context):
        self.setWtType("WContainerWidget", context)
        context['variableName']=camelCase(node.name())
        self.mainWidgetClass='Wt::WContainerWidget'
        self.mainWidgetName=node.name()
        self.process(node, context)
        
    def process_widget_QDockWidget(self, node, context):
        self.setWtType("WContainerWidget", context)
        context['variableName']=camelCase(node.name())
        self.mainWidgetClass='Wt::WContainerWidget'
        self.mainWidgetName=node.name()
        self.process(node, context)
    
    def process_widget_QDialog(self, node, context):
        self.setWtType("WDialog", context)
        context['variableName']=camelCase(node.name())
        self.mainWidgetClass='Wt::WDialog'
        self.mainWidgetName=node.name()
        self.process(node, context)
        
    def process_widget_QTabWidget(self, node, context):
        self.setWtType("WTabWidget", context)
        self.defineVariable(context)
        self.process(node, context)
        if 'children' in context:
            for child in context['children']:
                if 'className' in child and 'title' in child:
                    self.writeHeader("%s->addTab(%s, \"%s\");"%(context['variableName'], child['variableName'], child['title']))
                    
    def process_widget_QTableView(self, node, context):
        self.setWtType("WTableView", context)
        self.defineVariable(context)
        self.process(node, context)
        if 'minimumSize' in context and 'maximumSize' in context: #fixed size not in Qt Designer for QTableView force resize
            minimumSize=context['minimumSize'];
            maximumSize=context['maximumSize'];
#            self.writeHeader("int %(var)sWidth=%(var)s->width().toPixels(); int %(var)sHeight=%(var)s->height().toPixels();"%{"var":context['variableName']})
            if minimumSize.width == maximumSize.width:
                self.writeHeader("%s->setWidth(%s);"%(context['variableName'], minimumSize.width))
            if minimumSize.height == maximumSize.height:
                self.writeHeader("%s->setHeight(%s);"%(context['variableName'], minimumSize.height))
#            self.writeHeader("%(var)s->resize(Wt::WLength(%(var)sWidth), Wt::WLength(%(var)sHeight));"%{"var":context['variableName']})
        
    def process_widget_QTableWidget(self, node, context):
        self.setWtType("WTable", context)
        self.defineVariable(context)
        self.process(node, context)
        
    def process_widget_QTreeView(self, node, context):
        process_widget_QTreeWidget(self, node, context)
        
    def process_widget_QTreeWidget(self, node, context):
        self.setWtType("WTree", context)
        self.defineVariable(context)
        self.process(node, context)
                        
    def process_widget_QWidget(self, node, context):
        self.setWtType("WContainerWidget", context)
        self.defineVariable(context)
        self.process(node, context)
        
    def process_widget_QGroupBox(self, node, context):
        self.setWtType("WGroupBox", context)
        self.defineVariable(context)
        self.writeHeader('%s->setTitle("%s");'%(context['variableName'], node.property('title')))
        self.process(node, context)
        
    def process_widget_QLabel(self, node, context):
        self.setWtType("WLabel", context)
        self.defineVariable(context)
        self.writeHeader('%s->setText("%s");'%(context['variableName'], node.property('text')))
        self.process(node, context)
        
    def process_widget_QLineEdit(self, node, context):
        self.setWtType("WLineEdit", context)
        self.defineVariable(context)
        if node.property('text'):
            self.writeHeader('%s->setText("%s");'%(context['variableName'], node.property('text')))
        self.process(node, context)
    
    def process_widget_QComboBox(self, node, context):
        self.setWtType("WComboBox", context)
        self.defineVariable(context)
#        self.writeHeader('%s->setText("%s");'%(context['variableName'], node.property('text')))
        self.process(node, context)
        
    def process_widget_QPushButton(self, node, context):
        self.setWtType("WPushButton", context)
        self.defineVariable(context)
        self.writeHeader('%s->setText("%s");'%(context['variableName'], node.property('text')))
        self.process(node, context)
        
    def process_widget_QRadioButton(self, node, context):
        self.setWtType("WRadioButton", context)
        created=False
        if 'parentList' in context:
            groupboxParent=rfind(lambda parent:parent['className'] == 'Wt::WGroupBox', context['parentList'])
            if groupboxParent:
                if 'buttonGroup' not in groupboxParent:
                    emptyContext={}
                    self.setWtType('WButtonGroup', emptyContext)
                    groupboxParent['buttonGroup']="%sGroup"%groupboxParent['variableName']
                    self.writeHeader("Wt::WButtonGroup *%s=new Wt::WButtonGroup();"%groupboxParent['buttonGroup'])
                self.variables.append("%s *%s;"%(context['className'], context['variableName']))
                self.writeHeader("%s=new %s(\"%s\", %s);"%(context['variableName'], context['className'], node.property('text'), groupboxParent['variableName']))
                self.writeHeader("%s->addButton(%s);"%(groupboxParent['buttonGroup'], context['variableName']))
                created=True
        if not created:
            self.defineVariable(context)
            self.writeHeader('%s->setText("%s");'%(context['variableName'], node.property('text')))
        self.process(node, context)
    
    def process_widget_QCheckBox(self, node, context):
        self.setWtType("WCheckBox", context)
        self.defineVariable(context)
        self.writeHeader('%s->setText("%s");'%(context['variableName'], node.property('text')))
        self.process(node, context)
        
    #process functions for properties
    def process_property_default(self, node, context):
        context[node.name()]=node.value()
        
    def process_property_geometry(self, node, context):
        rect=node.find(tag='rect')
        if rect:
            if context['className'] not in ('Wt::WContainerWidget', 'Wt::WDialog'):
#                self.writeHeader("%s->setOffset(Wt::Left, Wt::WLength(%s));"%(context['variableName'], rect.x))
#                self.writeHeader("%s->setOffset(Wt::Top, Wt::WLength(%s));"%(context['variableName'], rect.x))
                self.writeHeader("%s->setOffsets(Wt::WLength(%s), Wt::Left);"%(context['variableName'], rect.x))
                self.writeHeader("%s->setOffsets(Wt::WLength(%s), Wt::Top);"%(context['variableName'], rect.y))
            self.writeHeader("%s->resize(Wt::WLength(%s), Wt::WLength(%s));"%(context['variableName'], rect.width, rect.height))
        
    def process_property_minimumSize(self, node, context):
        size=node.find(tag='size')
        if size:
            self.writeHeader("%s->setMinimumSize(Wt::WLength(%s), Wt::WLength(%s));"%(context['variableName'], size.width, size.height))
            context['minimumSize']=size
    
    def process_property_maximumSize(self, node, context):
        size=node.find(tag='size')
        if size:
            width=size.width
            height=size.height
            if width == '16777215':
                width='Wt::WLength::Auto'
            if height == '16777215':
                height='Wt::WLength::Auto'    
            self.writeHeader("%s->setMaximumSize(Wt::WLength(%s), Wt::WLength(%s));"%(context['variableName'], width, height))
            context['maximumSize']=size
    
#   def process_property_sizePolicy(self, node, context):
#        sizePolicy=node.find(tag='sizepolicy')
        
    #process functions for attributes
    def process_attribute_title(self, node, context):
        context['title']=node.value();
    
    
        
    #process functions for layouts
    def process_layout_QVBoxLayout(self, node, context):
        self.setWtType("WVBoxLayout", context)
        self.defineVariable(context)
        self.process_layout_items(node, context)
    
    def process_layout_QHBoxLayout(self, node, context):
        self.setWtType("WHBoxLayout", context)
        self.defineVariable(context)
        self.process_layout_items(node, context)
    
    def process_layout_QGridLayout(self, node, context):
        self.setWtType("WGridLayout", context)
        self.defineVariable(context)
        self.process_layout_items(node, context)
              
    def process_layout_QFormLayout(self, node, context):
        self.process_layout_QGridLayout(node, context) #no support for form layout using grid instead
        
    def process_layout_items(self, node, context):
        for item in node.findAll(tag='item'):
#            localContext={};
            localContext=context.copy()
            localContext['variableName']=context['variableName']
            localContext['className']=context['className']
            if context['className'] == 'Wt::WGridLayout':
                row=item.attribute('row')
                col=item.attribute('column')
            self.process(item, localContext)
            
            if 'children' in localContext:
                child=localContext['children'][0]
#                pprint(child)
                if 'className' in child:
#                    print child['className']
                    if child['className'] == 'spacer':
                        if context['className'] == 'Wt::WGridLayout':
                            if child['orientation'] == 'Qt::Horizontal':
                                self.writeHeader("%s->setColumnStretch(%s, 1);"%(context['variableName'], col))
                            else:
                                self.writeHeader("%s->setRowStretch(%s, 1);"%(context['variableName'], row))
                        else:
                            self.writeHeader("%s->addStretch(1);"%(context['variableName']))
                    else:
                        if child['className'] in layoutWidgets:
                            addFunction='addItem'
                        else:
                            addFunction='addWidget'
                        if context['className'] == 'Wt::WGridLayout':
                            self.writeHeader("%s->%s(%s, %s, %s);"%\
                                (context['variableName'], addFunction, child['variableName'], row, col))
                        else:
                            self.writeHeader("%s->%s(%s);"%\
                                (context['variableName'], addFunction, child['variableName']))
                
    #output functions
    def defineVariable(self, context):
        self.variables.append("%s *%s;"%\
                (context['className'], context['variableName']))
        if 'parentName' in context and 'parentClass' in context and context['parentClass'] not in nonParentWidgts:
            self.writeHeader("%s=new %s(%s);"%\
                (context['variableName'], context['className'], context['parentName']))
        else:
            self.writeHeader("%s=new %s();"%\
                (context['variableName'], context['className']))
    
    #utility functions
    def setWtType(self, typeName, context):
        context['className']="Wt::%s"%typeName
        if(typeName not in self.wtTypes):
            self.wtTypes.append(typeName)

    def writeHeader(self, string):
        print>>self.headerFile, "%s%s"%(self.indent, string)
        
    def tryFunctionCall(self, functionName, node, context):
        try:
            function=getattr(self, functionName)
        except AttributeError,e:
            self.printError("%s not found while parsing %s" % (functionName, node.trace()))
            return False
        function(node, context)
        return True
    
    def printError(self, string):
        if args.verbose:
            print>>sys.stderr, string
        return


#Script main section
op=optparse.OptionParser(usage="""usage: %prog [options] ui_file\n\nGenerates .h file from Qt .ui for use in Wt ui""")
op.add_option("--header", metavar="FILE", dest="header", help="generate .h file.")
op.add_option("-v", "--verbose", action="store_true", dest="verbose", help="print warnings")
(args, posargs)=op.parse_args()

if not posargs:
    print >>sys.stderr, "No ui file specified"
    sys.exit(-1)
elif len(posargs) > 1:
    print >>sys.stderr, "Multiple ui files specified"
    sys.exit(-1)
    
uiFileName=posargs[0]
miniDom=xml.dom.minidom.parse(uiFileName)
uiFile=MiniDomHelper(miniDom.childNodes[0])

headerFileName=args.header
tmpHeaderFileName=args.header+'_tmp'
tmpHeaderFile=tmpHeaderFileName and open(tmpHeaderFileName, 'w') or devnull()

context={}
context['indent']='        '
parser=UIXmlParser(tmpHeaderFile)
parser.process(uiFile, context)
tmpHeaderFile.close()

uiClassName="Ui_%s"%parser.mainWidgetName
headerFile=args.header and open(headerFileName, 'w') or devnull()
tmpHeaderFile=tmpHeaderFileName and open(tmpHeaderFileName, 'r') or devnull()

print>>headerFile, "//File generated from %s\n"%uiFileName
for wtType in parser.wtTypes:
    print>>headerFile, "#include <Wt/%s>"%(wtType)
    
print>>headerFile, "class %s"%(uiClassName)
print>>headerFile, "{"
print>>headerFile, "public:"
print>>headerFile, "    %(class)s::%(class)s()"%{'class':uiClassName}
print>>headerFile, "    {"
print>>headerFile, "    }"
print>>headerFile, "    void setupUi(%s *%s)"%(parser.mainWidgetClass, camelCase(parser.mainWidgetName))
print>>headerFile, "    {"
for line in tmpHeaderFile:
    headerFile.write(line)
print>>headerFile, "    }"
print>>headerFile, "protected:"
for variable in parser.variables:
    headerFile.write("    %s\n"%variable)
print>>headerFile, "};"
    
tmpHeaderFile.close()
headerFile.close()
os.remove(tmpHeaderFileName)